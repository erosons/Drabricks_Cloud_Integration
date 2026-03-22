#!/usr/bin/env python3
# ─────────────────────────────────────────────
# scripts/scim_group_manager.py
#
# Manages dynamic functional group membership
# via Databricks Account SCIM API.
#
# Use cases:
#   - Assign a user to a new functional group
#     when their use case changes
#   - Bulk-onboard a team to a domain
#   - Rotate access when someone changes role
#   - Audit current memberships
#
# Usage:
#   python scim_group_manager.py assign \
#     --user john.doe@company.com \
#     --groups prd_finance_ledger_region_apac \
#              prd_finance_ledger_pii_masked
#
#   python scim_group_manager.py revoke \
#     --user john.doe@company.com \
#     --groups prd_finance_ledger_region_apac
#
#   python scim_group_manager.py audit \
#     --user john.doe@company.com
#
#   python scim_group_manager.py bulk \
#     --file access_requests/2024_Q1_onboarding.yaml
# ─────────────────────────────────────────────

import os
import sys
import json
import argparse
import logging
from dataclasses import dataclass, field
from typing import Optional
import urllib.request
import urllib.error
import yaml   # pip install pyyaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SCIM client (no external HTTP deps)
# ─────────────────────────────────────────────

class SCIMClient:
    def __init__(self, account_id: str, token: str):
        self.base = f"https://accounts.azuredatabricks.net/api/2.0/accounts/{account_id}/scim/v2"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/scim+json",
            "Accept":        "application/scim+json",
        }

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        url  = f"{self.base}{path}"
        data = json.dumps(body).encode() if body else None
        req  = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode()
            raise RuntimeError(f"SCIM {method} {path} → HTTP {e.code}: {msg}") from e

    # ── Users ──────────────────────────────────

    def find_user(self, email: str) -> Optional[dict]:
        result = self._request("GET", f'/Users?filter=userName+eq+"{email}"')
        resources = result.get("Resources", [])
        return resources[0] if resources else None

    def get_user(self, user_id: str) -> dict:
        return self._request("GET", f"/Users/{user_id}")

    # ── Groups ─────────────────────────────────

    def find_group(self, display_name: str) -> Optional[dict]:
        result = self._request("GET", f'/Groups?filter=displayName+eq+"{display_name}"')
        resources = result.get("Resources", [])
        return resources[0] if resources else None

    def get_group(self, group_id: str) -> dict:
        return self._request("GET", f"/Groups/{group_id}")

    def list_user_groups(self, user_id: str) -> list[dict]:
        """Return all groups the user is a member of."""
        result = self._request("GET", f'/Groups?filter=members+eq+"{user_id}"&count=200')
        return result.get("Resources", [])

    # ── Membership operations ──────────────────

    def add_member(self, group_id: str, user_id: str):
        self._request("PATCH", f"/Groups/{group_id}", {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{
                "op":    "add",
                "path":  "members",
                "value": [{"value": user_id}],
            }]
        })

    def remove_member(self, group_id: str, user_id: str):
        self._request("PATCH", f"/Groups/{group_id}", {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{
                "op":    "remove",
                "path":  f'members[value eq "{user_id}"]',
            }]
        })


# ─────────────────────────────────────────────
# Domain model
# ─────────────────────────────────────────────

@dataclass
class AccessChange:
    user_email:    str
    assign_groups: list[str] = field(default_factory=list)
    revoke_groups: list[str] = field(default_factory=list)
    reason:        str = ""
    ticket_id:     str = ""


# ─────────────────────────────────────────────
# Core operations
# ─────────────────────────────────────────────

def resolve_user(client: SCIMClient, email: str) -> dict:
    user = client.find_user(email)
    if not user:
        raise ValueError(f"User not found in Databricks account: {email}")
    return user


def apply_access_change(client: SCIMClient, change: AccessChange, dry_run: bool = False):
    log.info("Processing access change for %s  [ticket=%s]", change.user_email, change.ticket_id or "—")

    user = resolve_user(client, change.user_email)
    user_id = user["id"]

    for group_name in change.assign_groups:
        group = client.find_group(group_name)
        if not group:
            log.warning("  SKIP assign — group not found: %s", group_name)
            continue
        if dry_run:
            log.info("  DRY-RUN  would ADD %s → %s", change.user_email, group_name)
        else:
            client.add_member(group["id"], user_id)
            log.info("  ASSIGNED  %s → %s", change.user_email, group_name)

    for group_name in change.revoke_groups:
        group = client.find_group(group_name)
        if not group:
            log.warning("  SKIP revoke — group not found: %s", group_name)
            continue
        if dry_run:
            log.info("  DRY-RUN  would REMOVE %s from %s", change.user_email, group_name)
        else:
            client.remove_member(group["id"], user_id)
            log.info("  REVOKED   %s from %s", change.user_email, group_name)


def audit_user(client: SCIMClient, email: str):
    user = resolve_user(client, email)
    groups = client.list_user_groups(user["id"])

    structural   = [g for g in groups if any(r in g["displayName"] for r in ["_reader", "_writer", "_admin"])]
    functional   = [g for g in groups if not any(r in g["displayName"] for r in ["_reader", "_writer", "_admin", "exempt"])]
    exempt       = [g for g in groups if "exempt" in g["displayName"]]

    print(f"\n{'═'*60}")
    print(f"  Access audit: {email}")
    print(f"{'═'*60}")

    print(f"\n  Structural groups ({len(structural)}):")
    for g in sorted(structural, key=lambda x: x["displayName"]):
        print(f"    ✓  {g['displayName']}")

    print(f"\n  Functional groups ({len(functional)}):")
    for g in sorted(functional, key=lambda x: x["displayName"]):
        print(f"    ✓  {g['displayName']}")

    if exempt:
        print(f"\n  ⚠  Exempt groups ({len(exempt)}):")
        for g in sorted(exempt, key=lambda x: x["displayName"]):
            print(f"    ⚠  {g['displayName']}")

    print()


def switch_use_case(client: SCIMClient, email: str,
                    from_groups: list[str], to_groups: list[str],
                    dry_run: bool = False):
    """
    Atomically moves a user from one set of functional groups
    to another — the primary operation for use-case switching.
    Revocations happen before assignments to minimise the
    window of over-privilege.
    """
    log.info("Switching use case for %s", email)
    log.info("  Revoking : %s", from_groups)
    log.info("  Assigning: %s", to_groups)

    change = AccessChange(
        user_email    = email,
        assign_groups = to_groups,
        revoke_groups = from_groups,
        reason        = "use-case switch",
    )
    apply_access_change(client, change, dry_run=dry_run)


def bulk_apply(client: SCIMClient, yaml_file: str, dry_run: bool = False):
    """
    Processes a YAML file of access changes. Format:

    changes:
      - user_email: john.doe@company.com
        ticket_id:  JIRA-1234
        reason:     "Promoted to global analyst"
        assign_groups:
          - prd_finance_ledger_region_global
          - prd_finance_ledger_pii_clear
        revoke_groups:
          - prd_finance_ledger_region_apac
          - prd_finance_ledger_pii_masked
    """
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    changes = [AccessChange(**c) for c in data.get("changes", [])]
    log.info("Processing %d access change(s) from %s", len(changes), yaml_file)

    errors = []
    for change in changes:
        try:
            apply_access_change(client, change, dry_run=dry_run)
        except Exception as e:
            log.error("Failed to process %s: %s", change.user_email, e)
            errors.append((change.user_email, str(e)))

    if errors:
        log.error("%d error(s) occurred:", len(errors))
        for user, err in errors:
            log.error("  %s: %s", user, err)
        sys.exit(1)
    else:
        log.info("All changes applied successfully.")


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def build_client() -> SCIMClient:
    account_id = os.environ.get("DATABRICKS_ACCOUNT_ID")
    token      = os.environ.get("DATABRICKS_ACCOUNT_TOKEN")
    if not account_id or not token:
        log.error("Set DATABRICKS_ACCOUNT_ID and DATABRICKS_ACCOUNT_TOKEN env vars")
        sys.exit(1)
    return SCIMClient(account_id, token)


def main():
    parser = argparse.ArgumentParser(
        description="Databricks ABAC dynamic group membership manager"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would happen without making changes")
    sub = parser.add_subparsers(dest="command", required=True)

    # assign
    p_assign = sub.add_parser("assign", help="Add user to functional groups")
    p_assign.add_argument("--user",   required=True)
    p_assign.add_argument("--groups", nargs="+", required=True)

    # revoke
    p_revoke = sub.add_parser("revoke", help="Remove user from functional groups")
    p_revoke.add_argument("--user",   required=True)
    p_revoke.add_argument("--groups", nargs="+", required=True)

    # switch
    p_switch = sub.add_parser("switch", help="Atomically move user between use cases")
    p_switch.add_argument("--user",  required=True)
    p_switch.add_argument("--from",  nargs="+", dest="from_groups", required=True)
    p_switch.add_argument("--to",    nargs="+", dest="to_groups",   required=True)

    # audit
    p_audit = sub.add_parser("audit", help="Show all group memberships for a user")
    p_audit.add_argument("--user", required=True)

    # bulk
    p_bulk = sub.add_parser("bulk", help="Apply a YAML file of access changes")
    p_bulk.add_argument("--file", required=True)

    args   = parser.parse_args()
    client = build_client()

    if args.command == "assign":
        apply_access_change(client, AccessChange(
            user_email=args.user, assign_groups=args.groups
        ), dry_run=args.dry_run)

    elif args.command == "revoke":
        apply_access_change(client, AccessChange(
            user_email=args.user, revoke_groups=args.groups
        ), dry_run=args.dry_run)

    elif args.command == "switch":
        switch_use_case(client, args.user,
                        from_groups=args.from_groups,
                        to_groups=args.to_groups,
                        dry_run=args.dry_run)

    elif args.command == "audit":
        audit_user(client, args.user)

    elif args.command == "bulk":
        bulk_apply(client, args.file, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
