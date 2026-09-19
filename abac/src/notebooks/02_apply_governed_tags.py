# Databricks notebook source
# MAGIC %md
# MAGIC # Step 2: Apply Governed Tags
# MAGIC Policy-driven tag application:
# MAGIC 1. Load `policies.yaml` → extract declared governed tag keys
# MAGIC 2. Check current tag state in UC (informational — what's already applied)
# MAGIC 3. Load `securables.yaml` → cross-check each tag exists in policies.yaml before applying
# MAGIC 4. Apply only tags declared in policies.yaml to deployed tables
# MAGIC
# MAGIC **Gate:** Tags in securables.yaml that are NOT in policies.yaml `governed_tags` are SKIPPED.

# COMMAND ----------

import yaml
import os

dbutils.widgets.text("config_path", "/Workspace/Users/samson.eromonsei@databricks.com/abac/configs", "Config Directory")
config_path = dbutils.widgets.get("config_path")

print(f"Config directory: {config_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load policies.yaml — extract governed tag keys

# COMMAND ----------

with open(os.path.join(config_path, "policies.yaml"), "r") as f:
    policies_config = yaml.safe_load(f)

# Build the set of tag keys declared in policies.yaml
policy_tag_keys = set()
policy_tag_details = {}
for tag_def in policies_config.get("governed_tags", []):
    key = tag_def["key"]
    policy_tag_keys.add(key)
    policy_tag_details[key] = {
        "description": tag_def.get("description", ""),
        "source": tag_def.get("source", "unknown"),
        "used_by": tag_def.get("used_by_policies", []),
    }

print(f"Governed tags declared in policies.yaml: {len(policy_tag_keys)}")
for key in sorted(policy_tag_keys):
    info = policy_tag_details[key]
    print(f"  {key} ({info['source']}) -> {info['used_by']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Verify governed tags exist in UC tag registry
# MAGIC Uses the Databricks SDK `tag_policies.list_tag_policies()` to query the
# MAGIC governed tag registry. Tags NOT in the registry cannot be applied.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Query the governed tag registry via SDK
registry_tag_keys = set(tp.tag_key for tp in w.tag_policies.list_tag_policies())

verified_tags = policy_tag_keys & registry_tag_keys
missing_from_registry = policy_tag_keys - registry_tag_keys

print("Governed tag registry verification:")
print("=" * 60)
print(f"  Registry contains {len(registry_tag_keys)} governed tag definitions")
print(f"  Policy tags verified in registry: {len(verified_tags)}")
for t in sorted(verified_tags):
    print(f"    \u2713 {t}")

if missing_from_registry:
    print(f"\n  \u26a0 Policy tags NOT in registry ({len(missing_from_registry)}):")
    for t in sorted(missing_from_registry):
        print(f"    \u2717 {t} \u2014 will be SKIPPED")
else:
    print(f"\n  \u2713 All policy tags exist in the governed tag registry")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Load securables.yaml — cross-check tags against policy declarations

# COMMAND ----------

with open(os.path.join(config_path, "securables.yaml"), "r") as f:
    securables_config = yaml.safe_load(f)

tables = securables_config.get("tables", [])

# Cross-check: collect all tags referenced in securables.yaml
securable_tags_used = set()
for table_def in tables:
    for tag_key in table_def.get("tags", {}).keys():
        securable_tags_used.add(tag_key)
    for col_def in table_def.get("columns", []):
        for tag_key in col_def.get("tags", {}).keys():
            securable_tags_used.add(tag_key)

# Tags in securables.yaml that are NOT declared in policies.yaml
undeclared_tags = securable_tags_used - policy_tag_keys

print(f"Tables in securables.yaml: {len(tables)}")
print(f"Unique tags referenced in securables.yaml: {len(securable_tags_used)}")
print(f"Tags also in policies.yaml governed_tags: {len(securable_tags_used & policy_tag_keys)}")
print(f"Tags NOT in policies.yaml (undeclared):    {len(undeclared_tags)}")

if undeclared_tags:
    print(f"\n\u26a0 Undeclared tags (in securables.yaml but NOT in policies.yaml governed_tags):")
    for t in sorted(undeclared_tags):
        print(f"    - {t}  ← will be SKIPPED")

# Eligible = declared in policies.yaml AND referenced in securables.yaml
print(f"\nEligible for application (declared in policies.yaml): {len(policy_tag_keys & securable_tags_used)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Apply declared governed tags
# MAGIC Only applies tags declared in policies.yaml `governed_tags` section.
# MAGIC Skips tables that don't exist and tags not in the policy registry.

# COMMAND ----------

applied = []
skipped_undeclared = []
skipped_not_in_registry = []
skipped_no_table = []
failed = []

print("Applying governed tags...")
print("=" * 60)

for table_def in tables:
    catalog = table_def["catalog"]
    schema = table_def["schema"]
    table_name = table_def["table_id"]
    table_fqn = f"{catalog}.{schema}.{table_name}"

    # Check if table exists before applying tags
    try:
        spark.sql(f"DESCRIBE TABLE {table_fqn}")
    except Exception:
        print(f"\n  \u23ed {table_fqn} — table does not exist, skipping")
        skipped_no_table.append(table_fqn)
        continue

    print(f"\n  \u25b6 {table_fqn}")

    # --- Apply table-level tags ---
    for tag_key, tag_value in table_def.get("tags", {}).items():
        if tag_key not in policy_tag_keys:
            skipped_undeclared.append(f"{table_fqn} | {tag_key}")
            print(f"      \u23ed TABLE {tag_key} — not in policies.yaml, skipped")
            continue
        if tag_key not in verified_tags:
            skipped_not_in_registry.append(f"{table_fqn} | {tag_key}")
            print(f"      \u23ed TABLE {tag_key} — not in tag registry, skipped")
            continue
        try:
            sql = f"ALTER TABLE {table_fqn} SET TAGS ('{tag_key}' = '{tag_value}')"
            spark.sql(sql)
            applied.append(f"{table_fqn} | {tag_key}={tag_value}")
            print(f"      \u2713 TABLE <- {tag_key}={tag_value or '(empty)'}")
        except Exception as e:
            error_msg = str(e)
            if "already" in error_msg.lower():
                applied.append(f"{table_fqn} | {tag_key}={tag_value} (already set)")
                print(f"      \u2713 TABLE <- {tag_key} (already set)")
            else:
                failed.append(f"{table_fqn} | {tag_key}: {error_msg[:60]}")
                print(f"      \u2717 TABLE <- {tag_key}: {error_msg[:60]}")

    # --- Apply column-level tags ---
    for col_def in table_def.get("columns", []):
        col_name = col_def["name"]
        col_tags = col_def.get("tags", {})
        if not col_tags:
            continue

        for tag_key, tag_value in col_tags.items():
            if tag_key not in policy_tag_keys:
                skipped_undeclared.append(f"{table_fqn}.{col_name} | {tag_key}")
                print(f"      \u23ed {col_name} <- {tag_key} — not in policies.yaml, skipped")
                continue
            if tag_key not in verified_tags:
                skipped_not_in_registry.append(f"{table_fqn}.{col_name} | {tag_key}")
                print(f"      \u23ed {col_name} <- {tag_key} — not in tag registry, skipped")
                continue
            try:
                sql = f"ALTER TABLE {table_fqn} ALTER COLUMN {col_name} SET TAGS ('{tag_key}' = '{tag_value}')"
                spark.sql(sql)
                applied.append(f"{table_fqn}.{col_name} | {tag_key}={tag_value}")
                print(f"      \u2713 {col_name} <- {tag_key}")
            except Exception as e:
                error_msg = str(e)
                if "already" in error_msg.lower():
                    applied.append(f"{table_fqn}.{col_name} | {tag_key} (already set)")
                    print(f"      \u2713 {col_name} <- {tag_key} (already set)")
                else:
                    failed.append(f"{table_fqn}.{col_name} | {tag_key}: {error_msg[:60]}")
                    print(f"      \u2717 {col_name} <- {tag_key}: {error_msg[:60]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("\n" + "=" * 60)
print("TAG APPLICATION SUMMARY")
print("=" * 60)
print(f"  Applied:                    {len(applied)}")
print(f"  Skipped (not in policies):  {len(skipped_undeclared)}")
print(f"  Skipped (not in registry):        {len(skipped_not_in_registry)}")
print(f"  Skipped (table missing):    {len(skipped_no_table)}")
print(f"  Failed:                     {len(failed)}")

if skipped_undeclared:
    print(f"\n\u26a0 Tags in securables.yaml but NOT declared in policies.yaml:")
    for item in skipped_undeclared:
        print(f"    - {item}")

if skipped_no_table:
    print(f"\n\u23ed Tables not yet deployed:")
    for t in skipped_no_table:
        print(f"    - {t}")

if failed:
    print(f"\n\u2717 Failures:")
    for f_item in failed:
        print(f"    - {f_item}")
    raise Exception(f"TAG APPLICATION HAD {len(failed)} FAILURE(S)")
else:
    print(f"\n\u2713 Complete — all eligible tags applied successfully")