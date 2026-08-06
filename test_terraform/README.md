# Entra ID App Registrations — Terraform Module

Provisions Azure Entra ID (AAD) app registrations, service principals, client secrets, and a Key Vault to store them. Implements the **three-app OAuth2 pattern**: a protected resource server, a daemon caller using Client Credentials, and a middle-tier API using the On-Behalf-Of (OBO) flow.

---

## The Three-App OAuth2 Pattern

Most real-world APIs need to handle two completely different caller types: **background services** that run without a user, and **interactive applications** that act on behalf of a signed-in user. These two cases require different OAuth2 grants, and each grant produces a token with different claims. Azure Entra ID handles both, but they must be configured separately on the resource server.

This module wires up all three roles:

| App | OAuth2 Role | Grant type used | Token claim validated |
|-----|-------------|-----------------|----------------------|
| `data_api` | Resource server | — (receives tokens) | `roles` (daemon) or `scp` (user) |
| `daemon_client` | Background service / SPN | Client Credentials | requests `roles` |
| `middle_tier` | User-facing API gateway | On-Behalf-Of (OBO) | requests `scp`, holds user identity |

### Why three apps and not one or two?

**Why not let `daemon_client` call `data_api` directly using a user token?**
Background Databricks jobs have no interactive user. They must authenticate as themselves using a client ID and secret — Client Credentials grant. This produces an `access_token` with `roles` claims (app roles), not `scp` claims (delegated scopes). The resource server needs to know which claim to check depending on who is calling.

**Why does the SPA need a `middle_tier` instead of calling `data_api` directly?**
The SPA runs in the browser — it cannot safely hold a client secret. The OBO flow requires a confidential client (one that can authenticate with a secret) to exchange the user's token for a downstream token. The `middle_tier` is that confidential client. It holds the user identity throughout and passes it downstream to `data_api` via the OBO exchange.

**Why does `middle_tier` expose its own scope (`access_as_user`)?**
The SPA requests `access_as_user` from `middle_tier`, not a scope on `data_api` directly. This lets `middle_tier` control what the SPA is allowed to do, independently of what `middle_tier` can do on the user's behalf downstream. The SPA never gets a token scoped to `data_api` — only `middle_tier` does.

### How the two flows stay separate on `data_api`

`data_api` exposes both **delegated scopes** (for OBO callers) and **app roles** (for daemon callers):

```
Caller type          Token contains     data_api validates
──────────────────   ────────────────   ───────────────────────────
daemon_client (SPN)  roles: DataReader  roles claim == "DataReader"
middle_tier (OBO)    scp: Data.Read     scp claim   == "Data.Read"
```

Both token types are v2 tokens. The `roles` claim is added via `optional_claims` in the app registration. The `scp` claim is emitted automatically by Entra ID for delegated flows — no explicit configuration needed.

### Pre-authorization and consent

Without pre-authorization, a user calling `middle_tier` would see **two** consent prompts: one for `middle_tier` and one for the OBO hop to `data_api`. Pre-authorization eliminates the second prompt — `data_api` declares that it trusts `middle_tier` to act on users' behalf, so Entra ID skips the second consent dialog entirely. This is configured via `azuread_application_pre_authorized` in Terraform.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Entra ID Tenant                            │
│                                                                     │
│   ┌──────────────┐   Client Credentials   ┌───────────────────┐    │
│   │ daemon_client│ ─────────────────────► │     data_api      │    │
│   │  (Databricks │   app role: DataReader  │  (resource server)│    │
│   │  job / SPN)  │                         │                   │    │
│   └──────────────┘                         │  Scopes:          │    │
│                                            │   Data.Read       │    │
│   ┌──────────────┐   OBO flow             │   Data.Write      │    │
│   │ middle_tier  │ ─────────────────────► │                   │    │
│   │ (API gateway)│   scope: Data.Read      │  App Roles:       │    │
│   └──────────────┘                         │   DataReader      │    │
│          ▲                                 │   DataWriter      │    │
│          │ access_as_user scope            └───────────────────┘    │
│   ┌──────┴───────┐                                                  │
│   │  Front-end   │                                                  │
│   │     SPA      │                                                  │
│   └──────────────┘                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## OAuth2 Flows

### 1. Client Credentials — `daemon_client → data_api`

Used by Databricks jobs or any background service that calls the API **without a user context**.

```
daemon_client                    Entra ID                  data_api
     │                               │                         │
     │  POST /token                  │                         │
     │  grant_type=client_credentials│                         │
     │  scope=api://data-api/.default│                         │
     │ ─────────────────────────────►│                         │
     │                               │                         │
     │  access_token {roles:[DataReader]}                      │
     │ ◄─────────────────────────────│                         │
     │                               │                         │
     │  GET /data   Bearer <token>   │                         │
     │ ──────────────────────────────────────────────────────► │
     │                  validate roles claim == DataReader      │
     │ ◄────────────────────────────────────────────────────── │
```

Token claim to validate on `data_api`: `roles` contains `"DataReader"` or `"DataWriter"`.

---

### 2. On-Behalf-Of (OBO) — Front-end → `middle_tier` → `data_api`

Used when a signed-in user calls the front-end SPA, which forwards the request through a middle-tier API that then calls `data_api` as that user.

```
SPA (user)          middle_tier              Entra ID             data_api
    │                    │                       │                    │
    │  login + consent   │                       │                    │
    │ ──────────────────────────────────────────►│                    │
    │  access_token {scp: access_as_user}        │                    │
    │ ◄──────────────────────────────────────────│                    │
    │                    │                       │                    │
    │  GET /resource     │                       │                    │
    │  Bearer <token>    │                       │                    │
    │ ──────────────────►│                       │                    │
    │                    │  POST /token (OBO)    │                    │
    │                    │  grant_type=urn:ietf:params:oauth2:grant-type:jwt-bearer
    │                    │  assertion=<user token>│                   │
    │                    │  scope=api://data-api/Data.Read            │
    │                    │ ─────────────────────►│                    │
    │                    │  access_token {scp: Data.Read}             │
    │                    │ ◄─────────────────────│                    │
    │                    │                       │                    │
    │                    │  GET /data  Bearer <data token>            │
    │                    │ ──────────────────────────────────────────►│
    │                    │              validate scp == Data.Read     │
    │                    │ ◄──────────────────────────────────────────│
```

Terraform only registers the app in Entra ID and stores the credentials. The token exchange logic in step 2 is typically handled by an auth library in your application — for example:

┌─────────┬─────────────────────────────────────────────┐
│  Stack  │                   Library
├─────────┼─────────────────────────────────────────────┤
│ Python  │ msal — acquire_token_on_behalf_of()
├─────────┼─────────────────────────────────────────────┤
│ Node.js │ @azure/msal-node — acquireTokenOnBehalfO
├─────────┼─────────────────────────────────────────────┤
│ .NET    │ Microsoft.Identity.Web — ITokenAcquisiti
├─────────┼─────────────────────────────────────────────┤
│ Java    │ msal4j — OnBehalfOfParameters
└─────────┴─────────────────────────────────────────────┘                                                                            
The middle_tier-client-id and middle_tier-client-secret secrets stored in Key Vault by this Terraform are what that library needs to authenticate as the confidential client during the O

Token claim to validate on `data_api`: `scp` contains `"Data.Read"` or `"Data.Write"`.

> **Pre-authorization**: `data_api` pre-authorizes `middle_tier`, so the user sees **one** consent prompt (for `access_as_user`) rather than two. The OBO hop is transparent to the user.

---

## App Registrations

| Key | Role | Exposes | Calls |
|-----|------|---------|-------|
| `data_api` | Resource server | `Data.Read` scope, `Data.Write` scope, `DataReader` role, `DataWriter` role | — |
| `daemon_client` | Client Credentials caller | — | `data_api` (DataReader role) |
| `middle_tier` | OBO intermediary | `access_as_user` scope | `data_api` (Data.Read scope via OBO) |

### Scope types

| Scope | Type | Meaning |
|-------|------|---------|
| `Data.Read` | `User` | User or admin can consent |
| `Data.Write` | `Admin` | Admin consent required |
| `access_as_user` | `User` | User or admin can consent |

### App role member types

| Role | `allowed_member_types` | Meaning |
|------|------------------------|---------|
| `DataReader` | `["Application"]` | Only service principals (no users) |
| `DataWriter` | `["Application"]` | Only service principals (no users) |

---

## Token Validation Reference

Use the `token_validation_configs` output to configure your API middleware.

| Field | Value |
|-------|-------|
| `authority` | `https://login.microsoftonline.com/<tenant_id>/v2.0` |
| `audience` | The app's `identifier_uri` (e.g. `api://web-apr-data-align-budget-data-api`) |
| `valid_issuers` | Both v1 (`sts.windows.net`) and v2 (`login.microsoftonline.com`) issuers |
| `delegated_claim` | `scp` — validate for OBO / user-delegated tokens |
| `app_role_claim` | `roles` — validate for Client Credentials tokens |

---

## File Structure

```
test_terraform/
├── provider.tf              # terraform block, required_providers, azurerm + azuread providers
├── main.tf                  # data sources (resource group, client config) and shared locals
├── variables.tf             # all variable schemas with validation — no defaults here
├── app_registrations.tf     # all Entra ID resources driven by var.app_registrations
├── keyvault.tf              # Key Vault + RBAC role assignments
├── outputs.tf               # per-app summaries, token validation configs, KV references
└── dev.environment.tfvars   # all values for the dev environment
```

---

## Adding a New App Registration

No HCL changes required. Add a new key block to `app_registrations` in the tfvars file:

```hcl
"my_new_service" = {
  display_name            = "my-new-service"
  identifier_uri          = "api://my-new-service"   # null if this is a client only
  homepage_url            = null
  sign_in_audience        = "AzureADMyOrg"
  secret_expiry           = "2027-01-01T00:00:00Z"
  require_role_assignment = true

  oauth2_scopes = {}
  app_roles     = {}

  client_credential_access = null
  obo_access               = null
}
```

Then:

```bash
terraform plan  -var-file=dev.environment.tfvars
terraform apply -var-file=dev.environment.tfvars
```

---

## Key Stability Rules

> Violating these causes UUID regeneration, which revokes all existing consent grants and breaks running integrations.

- **Never rename a map key** in `app_registrations` after first apply
- **Never rename an oauth2 scope value** (e.g. `"Data.Read"`) after first apply
- **Never rename an app role value** (e.g. `"DataReader"`) after first apply

To remove something, set `enabled = false` first, apply, then remove it in a second apply.

---

## Secrets

Every app registration gets two Key Vault secrets:

| Secret name | Contains |
|-------------|----------|
| `<reg_key>-client-id` | Application (client) ID |
| `<reg_key>-client-secret` | Client secret value |

Retrieve at runtime via Managed Identity — never hard-code secrets.

```bash
# Example: read daemon_client secret from Key Vault
az keyvault secret show \
  --vault-name <kv_name> \
  --name daemon-client-client-secret \
  --query value -o tsv
```

---

## Usage

```bash
# Initialise providers
terraform init

# Preview changes
terraform plan -var-file=dev.environment.tfvars

# Apply
terraform apply -var-file=dev.environment.tfvars

# View outputs (client IDs, scope URIs, KV references)
terraform output -json app_registrations
terraform output -json token_validation_configs
```

---

## Azure API Management (APIM)

App registrations and APIM operate at **different layers** — they are not alternatives, they are complementary. You need both.

### App registration — identity layer

App registration is not an API gateway. It tells Entra ID what an application is, what scopes and roles it exposes, and what other APIs it is allowed to call. It controls who can get a token and what that token claims. It has no concept of HTTP routing, rate limiting, or traffic. It lives entirely in Entra ID.

### APIM — traffic layer

APIM is a reverse proxy that sits in front of your actual API. It handles HTTP routing, rate limiting, throttling, request/response transformation, subscription keys, and the developer-facing API catalogue. It is not involved in issuing tokens — it only validates them after Entra ID has issued them, using its `validate-jwt` policy.

### How they work together

```
                    Entra ID (app registrations live here)
                         │  issues tokens
                         ▼
SPA ──► APIM ──────────────────────────────► data_api backend
        │  1. validate-jwt (checks scp/roles)
        │  2. rate limit
        │  3. route
        └──────────────────────────────────► other backends
```

The app registration defines **what the token says**. APIM decides **whether to let the request through** based on what the token says.

### Practical split

| Concern | Where it lives |
|---------|---------------|
| What scopes and roles exist | App registration (this Terraform config) |
| Who is pre-authorized for OBO | App registration (`azuread_application_pre_authorized`) |
| Who can get a token at all | Entra ID conditional access + `require_role_assignment` |
| Token validation on inbound requests | APIM `validate-jwt` policy |
| Rate limiting and quotas | APIM |
| API versioning and routing | APIM |
| Developer-facing API catalogue | APIM |

### Wiring APIM to this config

The `token_validation_configs` output from this module gives APIM exactly what it needs for its `validate-jwt` policy — the `authority`, `audience`, and `valid_issuers` for each resource server. APIM does not replace the app registrations; it consumes them.

If APIM needs to call `data_api` using its own Managed Identity (Pattern 1 below), add APIM's managed identity object ID to `keyvault_workload_principal_ids` in the tfvars so it gets `Key Vault Secrets User` access automatically.

### APIM patterns

**Pattern 1 — APIM as gateway only**
APIM sits in front of `data_api` and validates tokens. `middle_tier` continues to own the OBO exchange. Nothing changes in this Terraform config except adding APIM's managed identity to `keyvault_workload_principal_ids`.

```
SPA ──► middle_tier (OBO) ──► APIM ──► data_api backend
daemon_client ──────────────► APIM ──► data_api backend
```

**Pattern 2 — APIM replaces `middle_tier`**
APIM becomes the confidential client that performs the OBO exchange via a `send-request` policy. Remove `middle_tier` from the tfvars and add an `apim_gateway` entry instead:

```hcl
"apim_gateway" = {
  display_name            = "web-apr-data-align-budget-apim"
  identifier_uri          = "api://web-apr-data-align-budget-apim"
  homepage_url            = null
  sign_in_audience        = "AzureADMyOrg"
  secret_expiry           = "2027-01-01T00:00:00Z"
  require_role_assignment = true
  oauth2_scopes = {
    "access_as_user" = {
      type                       = "User"
      enabled                    = true
      admin_consent_display_name = "Access as user"
      admin_consent_description  = "Allows the app to call the API gateway as the signed-in user."
      user_consent_display_name  = "Access as you"
      user_consent_description   = "Access the API gateway as yourself."
    }
  }
  app_roles                = {}
  client_credential_access = null
  obo_access = {
    target_app_reg_key = "data_api"
    requested_scopes   = ["Data.Read"]
    pre_authorize      = true
  }
}
```

APIM reads `apim-gateway-client-id` and `apim-gateway-client-secret` from Key Vault at startup using its Managed Identity, then uses those credentials in its OBO token exchange policy.

**Pattern 3 — APIM as a daemon caller**
APIM calls `data_api` on its own behalf with no user context (e.g. a scheduled aggregation endpoint). Add it as a client credentials caller:

```hcl
"apim_daemon" = {
  display_name             = "web-apr-data-align-budget-apim-daemon"
  identifier_uri           = null
  homepage_url             = null
  sign_in_audience         = "AzureADMyOrg"
  secret_expiry            = "2027-01-01T00:00:00Z"
  require_role_assignment  = false
  oauth2_scopes            = {}
  app_roles                = {}
  client_credential_access = {
    target_app_reg_key = "data_api"
    assigned_roles     = ["DataReader"]
  }
  obo_access = null
}
```

---

## Known Limitations

- **Key Vault name length**: Azure enforces a 24-character limit. Keep `project_name` under 14 characters to avoid an apply failure (`kv-<name>-<6char suffix>` = max 24).
- **Secret expiry**: All secrets are set to a fixed date. Rotate before expiry by tainting the `azuread_application_password` resources and re-applying.
- **No backend configured**: State is stored locally. For team use, add a `backend` block in `provider.tf` pointing to Azure Blob Storage.
