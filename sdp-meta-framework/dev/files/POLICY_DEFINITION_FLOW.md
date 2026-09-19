# Policy Definition Flow - From YAML to Enforcement

## File Structure

Your policy definitions live in these local files:

```
/Users/samson.eromonsei/sp-framework/sdp-meta-framework/
├── conf/abac/
│   ├── bronze_securables.yml   ← CATALOG/SCHEMA/TABLE definitions (Bronze layer)
│   └── silver_securables.yml   ← CATALOG/SCHEMA/TABLE definitions (Silver layer)
├── abac/
│   └── configs/
│       └── policies.yml        ← POLICY definitions (UDFs, row filters, column masks)
└── databricks.yml              ← Sync configuration
```

## Deployment Flow

### 1. Bundle Deploy
```bash
databricks bundle deploy --profile fevm-machine
```

**What happens:**
```
Local files:
  conf/abac/bronze_securables.yml
  conf/abac/silver_securables.yml
  abac/configs/policies.yml
       ↓
  [Bundle Sync]
       ↓
Workspace files:
  /Workspace/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac/bronze_securables.yml
  /Workspace/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac/silver_securables.yml
  /Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac/configs/policies.yml
```

### 2. Notebook 01 - Load Definitions

**Reads from deployed workspace paths:**

```python
# spec_table_reader.py loads:
bronze_path = "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac/bronze_securables.yml"
silver_path = "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac/silver_securables.yml"
policies_path = "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac/configs/policies.yml"
```

**Extracts hierarchy:**
```
bronze_securables.yml
├── catalogs: []           (optional)
├── schemas:               (with policy_bindings + tags)
│   └── tables:            (with policy_bindings + tags)
│       └── columns        (optional explicit columns)

silver_securables.yml
├── catalogs: []           (optional)
├── schemas:               (with policy_bindings + tags)
│   └── tables:            (with policy_bindings + tags)
│       └── columns        (optional explicit columns)

policies.yml
├── governed_tags:         (tag definitions)
├── udf_registry:          (function definitions)
└── policies:              (row_filters + column_masks)
```

### 3. Apply Inheritance

```python
from policy_inheritance import apply_inheritance_to_manifest
manifest = apply_inheritance_to_manifest(manifest)
```

**Result:**
```
Each table now has:
  - policy_bindings: [direct + inherited from catalog/schema]
  - inherited_policy_bindings: [what came from catalog/schema]
  - tags: {catalog tags + schema tags + table tags}
```

### 4. Cache Manifest

```python
# Store in temp table for notebooks 02-06
temp_table = f"{catalog}.{sdp_meta_schema}.manifest_cache"
```

## Your Configuration Files

### bronze_securables.yml Structure

```yaml
api_version: governance.databricks.com/v2
kind: SecurableRegistry

# Optional: Catalog-level policies (all schemas/tables inherit)
catalogs:
  - catalog_id: general_use
    policy_bindings:
      - global_audit_filter     # ALL tables in catalog inherit
    tags:
      compliance: "sox"          # ALL tables inherit

# Schema-level policies (all tables in schema inherit)
schemas:
  - schema_id: hr
    catalog: general_use
    policy_bindings:
      - mnpi_row_filtering      # ALL hr tables inherit
    tags:
      mnpi: ""                   # ALL hr tables inherit
    grants:
      - group: hr_data_readers
        privileges: [USE SCHEMA, SELECT]
    
    tables:
      # Tables inherit schema-level policies + tags
      - table_id: employees
        description: "Employee records"
        # Inherits: mnpi_row_filtering policy + mnpi tag
        # Can add table-specific:
        policy_bindings:
          - custom_table_filter   # Added to inherited policies
        
  - schema_id: finance
    catalog: general_use
    policy_bindings: []          # No schema-level policies
    
    tables:
      - table_id: accounts_payable
        policy_bindings:
          - mnpi_column_masking   # Table-level only
        tags:
          mnpi: ""                 # Table-level tag
        information_schema: true   # Mask ALL columns
        
      - table_id: cash_flow
        policy_bindings:
          - mnpi_column_masking
        tags:
          mnpi: ""
        information_schema: false  # Only mask specified columns
        mnpi_masked_columns:
          - amount
          - credit_card
```

### policies.yml Structure

```yaml
# Tag definitions
governed_tags:
  - key: mnpi
    description: "Material Non-Public Information"
    scope: table
    used_by_policies: [mnpi_row_filtering, mnpi_column_masking]

# UDF definitions
udf_registry:
  target_catalog: general_use
  target_schema: platform_admin
  
  row_filters:
    - function_id: filter_mnpi_access
      parameters:
        - name: group_name
          type: STRING
      returns: BOOLEAN
      body: |
        RETURN is_account_group_member(group_name);
  
  column_masks:
    - function_id: mask_mnpi_value
      parameters:
        - name: group_name
          type: STRING
        - name: value
          type: STRING
      returns: STRING
      body: |
        CASE 
          WHEN is_account_group_member(group_name) THEN value
          ELSE '[MNPI RESTRICTED]'
        END;

# Policy definitions
policies:
  row_filters:
    - policy_id: mnpi_row_filtering
      scope_level: SCHEMA              # Can be: CATALOG, SCHEMA, or TABLE
      udf: filter_mnpi_access
      udf_bindings:
        group_name: "{schema}_mnpi_approved"   # {schema} resolved at deploy time
  
  column_masks:
    - policy_id: mnpi_column_masking
      scope_level: TABLE
      udf: mask_mnpi_value
      udf_bindings:
        group_name: "{schema}_mnpi_approved"
```

## Inheritance Examples

### Example 1: Schema-Level Policy (All tables inherit)

**Definition in bronze_securables.yml:**
```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - mnpi_row_filtering     # Defined at schema level
    tables:
      - table_id: employees    # No policy_bindings specified
      - table_id: payroll      # No policy_bindings specified
      - table_id: benefits     # No policy_bindings specified
```

**Result after inheritance:**
```
Table: general_use.hr.employees
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
  Policy scope: SCHEMA

Table: general_use.hr.payroll
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
  Policy scope: SCHEMA

Table: general_use.hr.benefits
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
  Policy scope: SCHEMA
```

**Policy created in Notebook 04:**
```sql
-- ONE policy for entire schema (not per table)
CREATE OR REPLACE POLICY mnpi_row_filtering
ON SCHEMA general_use.hr
FOR ROW FILTER
USING (general_use.platform_admin.filter_mnpi_access('hr_mnpi_approved'));
```

### Example 2: Table-Level Override

**Definition in bronze_securables.yml:**
```yaml
schemas:
  - schema_id: finance
    policy_bindings:
      - standard_masking      # Default for schema
    tables:
      - table_id: accounts_payable
        # Inherits standard_masking
        
      - table_id: sensitive_deals
        policy_bindings:
          - enhanced_masking   # Overrides schema default
```

**Result after inheritance:**
```
Table: general_use.finance.accounts_payable
  Direct policies: []
  Inherited policies: [standard_masking]
  Policy scope: SCHEMA

Table: general_use.finance.sensitive_deals
  Direct policies: [enhanced_masking]
  Inherited policies: []
  Policy scope: TABLE (override)
```

**Policies created in Notebook 04:**
```sql
-- Schema-level for accounts_payable
CREATE OR REPLACE POLICY standard_masking
ON SCHEMA general_use.finance
...

-- Table-level override for sensitive_deals
CREATE OR REPLACE POLICY enhanced_masking
ON TABLE general_use.finance.sensitive_deals
...
```

### Example 3: Catalog-Level Policy

**Definition in bronze_securables.yml:**
```yaml
catalogs:
  - catalog_id: general_use
    policy_bindings:
      - global_audit         # ALL schemas/tables inherit
    tags:
      compliance: "sox"       # ALL tables inherit

schemas:
  - schema_id: hr
    catalog: general_use
    tables:
      - table_id: employees  # Inherits global_audit + compliance tag
```

**Result after inheritance:**
```
Table: general_use.hr.employees
  Direct policies: []
  Inherited policies: [global_audit]
  Tags: {compliance: "sox"}
  Policy scope: CATALOG
```

**Policy created in Notebook 04:**
```sql
-- ONE policy for entire catalog
CREATE OR REPLACE POLICY global_audit
ON CATALOG general_use
FOR ROW FILTER
...
```

## Path Verification

To verify the paths are correct:

```python
# In Databricks notebook
# Check that files exist at deployed paths
dbutils.fs.ls("/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac/")
# Should show: bronze_securables.yml, silver_securables.yml

dbutils.fs.ls("/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac/configs/")
# Should show: policies.yml
```

## Key Points

✅ **Local files** in `conf/abac/` are your source of truth

✅ **Bundle deploy** syncs them to workspace deployment path

✅ **Notebook 01** reads from workspace deployment path (not Volumes)

✅ **Inheritance engine** cascades catalog → schema → table policies

✅ **Notebook 04** creates policies at their original scope only

## Making Changes

1. **Edit local YAML files:**
   ```bash
   vim conf/abac/bronze_securables.yml
   vim conf/abac/silver_securables.yml
   vim abac/configs/policies.yml
   ```

2. **Redeploy:**
   ```bash
   databricks bundle deploy --profile fevm-machine
   ```

3. **Run notebooks 01-06** to apply changes

That's it! Your local YAML files → deployed files → loaded by notebooks → policies created.
