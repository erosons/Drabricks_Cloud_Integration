"""
ABAC Governance Manager — Databricks App

A Gradio-based UI for non-technical users to:
1. View and manage policy principals (TO / EXCEPT groups)
2. Add/remove groups from policy enforcement
3. Manage RBAC grants on table configs
4. View drift detection results
5. Trigger governance deployment

All changes are written back to the YAML config files,
maintaining the config-as-code approach.
"""

import os
import yaml
import glob
import json
import gradio as gr
from datetime import datetime
from copy import deepcopy
from typing import Dict, List, Any, Tuple

# Configuration
POLICIES_FILE = os.environ.get(
    "POLICIES_FILE",
    "/Workspace/Users/samson.eromonsei@databricks.com/abac-mvp2/configs/policies.yaml"
)
SECURABLES_DIR = os.environ.get(
    "SECURABLES_DIR",
    "/Workspace/Users/samson.eromonsei@databricks.com/abac-mvp2/configs/securables"
)
CHANGE_LOG_FILE = os.environ.get(
    "CHANGE_LOG_FILE",
    "/Workspace/Users/samson.eromonsei@databricks.com/abac-mvp2/configs/change_log.json"
)


# =============================================================================
# YAML HELPERS
# =============================================================================

def load_policies() -> Dict[str, Any]:
    """Load the policies.yaml file."""
    with open(POLICIES_FILE, "r") as f:
        return yaml.safe_load(f)


def save_policies(data: Dict[str, Any]):
    """Save policies.yaml with preserved formatting."""
    with open(POLICIES_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)


def load_securable_files() -> List[Tuple[str, Dict[str, Any]]]:
    """Load all table config files from securables directory."""
    pattern = os.path.join(SECURABLES_DIR, "**", "*.yaml")
    files = glob.glob(pattern, recursive=True)
    results = []
    for f in sorted(files):
        if os.path.basename(f).startswith("_"):
            continue
        with open(f, "r") as fh:
            data = yaml.safe_load(fh)
            if data and "table_id" in data:
                results.append((f, data))
    return results


def save_securable_file(filepath: str, data: Dict[str, Any]):
    """Save a single table config file."""
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=120)


def log_change(action: str, details: Dict[str, Any], user: str = "app_user"):
    """Append a change to the audit log."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user,
        "action": action,
        "details": details,
    }
    log = []
    if os.path.exists(CHANGE_LOG_FILE):
        with open(CHANGE_LOG_FILE, "r") as f:
            log = json.load(f)
    log.append(entry)
    with open(CHANGE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


# =============================================================================
# POLICY PRINCIPAL MANAGEMENT
# =============================================================================

def get_all_policies() -> List[str]:
    """Get list of all policy IDs."""
    policies = load_policies()
    policy_ids = []
    for p in policies.get("policies", {}).get("row_filters", []):
        policy_ids.append(p["policy_id"])
    for p in policies.get("policies", {}).get("column_masks", []):
        policy_ids.append(p["policy_id"])
    return policy_ids


def get_policy_details(policy_id: str) -> str:
    """Get formatted details of a specific policy."""
    policies = load_policies()
    all_policies = (
        policies.get("policies", {}).get("row_filters", []) +
        policies.get("policies", {}).get("column_masks", [])
    )
    for p in all_policies:
        if p["policy_id"] == policy_id:
            details = [
                f"**Policy:** {p['policy_id']}",
                f"**Description:** {p.get('description', 'N/A')}",
                f"**Scope:** {p.get('scope_level', 'N/A')}",
                f"**UDF:** {p.get('udf', 'N/A')}",
                f"\n**TO (enforced on):**",
            ]
            for group in p.get("principals", {}).get("to", []):
                details.append(f"  - {group}")
            details.append(f"\n**EXCEPT (bypasses policy):**")
            for group in p.get("principals", {}).get("except", []):
                details.append(f"  - {group}")
            return "\n".join(details)
    return "Policy not found."


def add_principal_to_policy(
    policy_id: str, group_name: str, principal_type: str
) -> str:
    """Add a group to a policy's TO or EXCEPT list."""
    if not group_name.strip():
        return "❌ Group name cannot be empty."

    group_name = group_name.strip()
    policies = load_policies()

    # Find the policy in row_filters or column_masks
    for section in ["row_filters", "column_masks"]:
        for p in policies.get("policies", {}).get(section, []):
            if p["policy_id"] == policy_id:
                target_list = p.setdefault("principals", {}).setdefault(
                    principal_type, []
                )
                if group_name in target_list:
                    return f"⚠️ Group '{group_name}' already in {principal_type} list."

                target_list.append(group_name)
                save_policies(policies)
                log_change(
                    "add_principal",
                    {
                        "policy_id": policy_id,
                        "group": group_name,
                        "principal_type": principal_type,
                    },
                )
                return (
                    f"\u2713 Added '{group_name}' to **{principal_type}** list "
                    f"of policy '{policy_id}'."
                )

    return f"❌ Policy '{policy_id}' not found."


def remove_principal_from_policy(
    policy_id: str, group_name: str, principal_type: str
) -> str:
    """Remove a group from a policy's TO or EXCEPT list."""
    if not group_name.strip():
        return "❌ Group name cannot be empty."

    group_name = group_name.strip()
    policies = load_policies()

    for section in ["row_filters", "column_masks"]:
        for p in policies.get("policies", {}).get(section, []):
            if p["policy_id"] == policy_id:
                target_list = p.get("principals", {}).get(principal_type, [])
                if group_name not in target_list:
                    return f"⚠️ Group '{group_name}' not found in {principal_type} list."

                target_list.remove(group_name)
                save_policies(policies)
                log_change(
                    "remove_principal",
                    {
                        "policy_id": policy_id,
                        "group": group_name,
                        "principal_type": principal_type,
                    },
                )
                return (
                    f"\u2713 Removed '{group_name}' from **{principal_type}** list "
                    f"of policy '{policy_id}'."
                )

    return f"❌ Policy '{policy_id}' not found."


# =============================================================================
# GRANT MANAGEMENT
# =============================================================================

def get_all_tables() -> List[str]:
    """Get list of all managed table FQNs."""
    tables = load_securable_files()
    return [
        f"{d['catalog']}.{d['schema']}.{d['table_id']}"
        for _, d in tables
    ]


def get_table_grants(table_fqn: str) -> str:
    """Get formatted grants for a table."""
    tables = load_securable_files()
    for filepath, data in tables:
        fqn = f"{data['catalog']}.{data['schema']}.{data['table_id']}"
        if fqn == table_fqn:
            grants = data.get("grants", [])
            if not grants:
                return f"No explicit grants configured for {table_fqn}.\nTemplate defaults will apply."
            lines = [f"**Grants for {table_fqn}:**\n"]
            for g in grants:
                group = g.get("group", g.get("role", "unknown"))
                privs = ", ".join(g.get("privileges", []))
                lines.append(f"  - **{group}**: {privs}")
            return "\n".join(lines)
    return "Table not found."


def add_grant_to_table(
    table_fqn: str, group_name: str, privileges: str
) -> str:
    """Add a grant entry to a table's config."""
    if not group_name.strip() or not privileges.strip():
        return "❌ Group name and privileges are required."

    group_name = group_name.strip()
    priv_list = [p.strip() for p in privileges.split(",")]

    tables = load_securable_files()
    for filepath, data in tables:
        fqn = f"{data['catalog']}.{data['schema']}.{data['table_id']}"
        if fqn == table_fqn:
            grants = data.setdefault("grants", [])

            # Check if group already exists
            for g in grants:
                if g.get("group") == group_name:
                    return f"⚠️ Group '{group_name}' already has grants. Remove first to update."

            grants.append({
                "group": group_name,
                "privileges": priv_list,
            })
            save_securable_file(filepath, data)
            log_change(
                "add_grant",
                {
                    "table": table_fqn,
                    "group": group_name,
                    "privileges": priv_list,
                },
            )
            return (
                f"\u2713 Added grant for '{group_name}' on {table_fqn}: "
                f"{', '.join(priv_list)}"
            )

    return f"❌ Table '{table_fqn}' not found in config."


def remove_grant_from_table(table_fqn: str, group_name: str) -> str:
    """Remove a grant entry from a table's config."""
    if not group_name.strip():
        return "❌ Group name is required."

    group_name = group_name.strip()
    tables = load_securable_files()
    for filepath, data in tables:
        fqn = f"{data['catalog']}.{data['schema']}.{data['table_id']}"
        if fqn == table_fqn:
            grants = data.get("grants", [])
            original_len = len(grants)
            data["grants"] = [g for g in grants if g.get("group") != group_name]

            if len(data["grants"]) == original_len:
                return f"⚠️ Group '{group_name}' not found in grants for {table_fqn}."

            save_securable_file(filepath, data)
            log_change(
                "remove_grant",
                {"table": table_fqn, "group": group_name},
            )
            return f"\u2713 Removed grant for '{group_name}' from {table_fqn}."

    return f"❌ Table '{table_fqn}' not found in config."


# =============================================================================
# CHANGE LOG VIEWER
# =============================================================================

def get_change_log() -> str:
    """Get formatted change log."""
    if not os.path.exists(CHANGE_LOG_FILE):
        return "No changes recorded yet."

    with open(CHANGE_LOG_FILE, "r") as f:
        log = json.load(f)

    if not log:
        return "No changes recorded yet."

    lines = ["| Timestamp | Action | Details |\n|---|---|---|"]
    for entry in reversed(log[-50:]):  # Show last 50
        ts = entry["timestamp"][:19]
        action = entry["action"]
        details = json.dumps(entry["details"], separators=(",", ":"))[:80]
        lines.append(f"| {ts} | {action} | {details} |")

    return "\n".join(lines)


# =============================================================================
# GRADIO UI
# =============================================================================

def build_app() -> gr.Blocks:
    """Build the Gradio application."""

    with gr.Blocks(
        title="ABAC Governance Manager",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown("# 🛡️ ABAC Governance Manager")
        gr.Markdown(
            "Manage policy principals (TO/EXCEPT) and table grants "
            "without editing YAML directly."
        )

        with gr.Tabs():
            # -----------------------------------------------------------------
            # TAB 1: Policy Principal Management
            # -----------------------------------------------------------------
            with gr.Tab("🔐 Policy Principals"):
                gr.Markdown("### Manage who policies apply TO and who is EXCEPT")

                with gr.Row():
                    policy_dropdown = gr.Dropdown(
                        choices=get_all_policies(),
                        label="Select Policy",
                        interactive=True,
                    )
                    refresh_policies_btn = gr.Button("🔄 Refresh", size="sm")

                policy_details_output = gr.Markdown("Select a policy to view details.")
                policy_dropdown.change(
                    fn=get_policy_details,
                    inputs=policy_dropdown,
                    outputs=policy_details_output,
                )

                gr.Markdown("---")
                gr.Markdown("#### Add Principal")
                with gr.Row():
                    add_group_input = gr.Textbox(
                        label="Group Name",
                        placeholder="e.g., finance_data_readers",
                    )
                    add_type_radio = gr.Radio(
                        choices=["to", "except"],
                        label="Add to list",
                        value="to",
                    )
                    add_btn = gr.Button("➕ Add Principal", variant="primary")

                add_result = gr.Markdown("")
                add_btn.click(
                    fn=add_principal_to_policy,
                    inputs=[policy_dropdown, add_group_input, add_type_radio],
                    outputs=add_result,
                )

                gr.Markdown("#### Remove Principal")
                with gr.Row():
                    rm_group_input = gr.Textbox(
                        label="Group Name to Remove",
                        placeholder="e.g., finance_data_readers",
                    )
                    rm_type_radio = gr.Radio(
                        choices=["to", "except"],
                        label="Remove from list",
                        value="to",
                    )
                    rm_btn = gr.Button("➖ Remove Principal", variant="stop")

                rm_result = gr.Markdown("")
                rm_btn.click(
                    fn=remove_principal_from_policy,
                    inputs=[policy_dropdown, rm_group_input, rm_type_radio],
                    outputs=rm_result,
                )

                def refresh_policies():
                    return gr.Dropdown(choices=get_all_policies())

                refresh_policies_btn.click(
                    fn=refresh_policies, outputs=policy_dropdown
                )

            # -----------------------------------------------------------------
            # TAB 2: Table Grant Management
            # -----------------------------------------------------------------
            with gr.Tab("📊 Table Grants"):
                gr.Markdown("### Manage RBAC grants on table configurations")

                with gr.Row():
                    table_dropdown = gr.Dropdown(
                        choices=get_all_tables(),
                        label="Select Table",
                        interactive=True,
                    )
                    refresh_tables_btn = gr.Button("🔄 Refresh", size="sm")

                table_grants_output = gr.Markdown("Select a table to view grants.")
                table_dropdown.change(
                    fn=get_table_grants,
                    inputs=table_dropdown,
                    outputs=table_grants_output,
                )

                gr.Markdown("---")
                gr.Markdown("#### Add Grant")
                with gr.Row():
                    grant_group_input = gr.Textbox(
                        label="Group Name",
                        placeholder="e.g., analytics_team",
                    )
                    grant_privs_input = gr.Textbox(
                        label="Privileges (comma-separated)",
                        placeholder="USE CATALOG, BROWSE, USE SCHEMA, SELECT",
                    )
                    grant_add_btn = gr.Button("➕ Add Grant", variant="primary")

                grant_add_result = gr.Markdown("")
                grant_add_btn.click(
                    fn=add_grant_to_table,
                    inputs=[table_dropdown, grant_group_input, grant_privs_input],
                    outputs=grant_add_result,
                )

                gr.Markdown("#### Remove Grant")
                with gr.Row():
                    grant_rm_group = gr.Textbox(
                        label="Group Name to Remove",
                        placeholder="e.g., analytics_team",
                    )
                    grant_rm_btn = gr.Button("➖ Remove Grant", variant="stop")

                grant_rm_result = gr.Markdown("")
                grant_rm_btn.click(
                    fn=remove_grant_from_table,
                    inputs=[table_dropdown, grant_rm_group],
                    outputs=grant_rm_result,
                )

                def refresh_tables():
                    return gr.Dropdown(choices=get_all_tables())

                refresh_tables_btn.click(
                    fn=refresh_tables, outputs=table_dropdown
                )

            # -----------------------------------------------------------------
            # TAB 3: Change Log / Audit Trail
            # -----------------------------------------------------------------
            with gr.Tab("📝 Change Log"):
                gr.Markdown("### Recent configuration changes")
                change_log_output = gr.Markdown(get_change_log())
                refresh_log_btn = gr.Button("🔄 Refresh Log")
                refresh_log_btn.click(
                    fn=get_change_log, outputs=change_log_output
                )

            # -----------------------------------------------------------------
            # TAB 4: Overview / Help
            # -----------------------------------------------------------------
            with gr.Tab("ℹ️ Help"):
                gr.Markdown("""
### How This App Works

**Policy Principals (TO / EXCEPT):**
- **TO**: Groups that the policy is enforced ON (they see masked/filtered data)
- **EXCEPT**: Groups that BYPASS the policy (they see cleartext/full data)

**Example:** To give the `finance_analysts` group cleartext access to email columns:
1. Go to "Policy Principals" tab
2. Select `pii_email_masking`
3. Add `finance_analysts` to the **except** list

**Table Grants:**
- Grants define which groups can access a table and with what privileges
- Common privileges: `USE CATALOG`, `BROWSE`, `USE SCHEMA`, `SELECT`, `MODIFY`

**Deployment:**
- Changes made here update the YAML config files
- Run the governance deployment pipeline to apply changes to Unity Catalog
- All changes are logged in the Change Log tab for audit
                """)

    return app


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    app = build_app()
    app.launch()
