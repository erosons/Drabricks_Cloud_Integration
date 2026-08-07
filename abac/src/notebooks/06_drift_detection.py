# Databricks notebook source
# MAGIC %md
# MAGIC # Step 6: Drift Detection
# MAGIC Scheduled daily to detect configuration drift between desired state and UC.

# COMMAND ----------

dbutils.widgets.text("catalog", "general_use", "Target Catalog")
dbutils.widgets.text("schema", "customer", "Target Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# Expected state: columns that should have governed tags
expected_tags = {
    f"{catalog}.{schema}.customer_profile.email": "class.email_address",
    f"{catalog}.{schema}.customer_profile.phone_number": "class.phone_number",
    f"{catalog}.{schema}.customer_profile.date_of_birth": "class.date_of_birth",
}

# Expected policies on the schema
expected_policies = [
    "mask_email_policy",
    "mask_phone_policy",
    "mask_dob_policy",
]

# COMMAND ----------

# Check tag drift
print("Checking tag assignments...")
print("=" * 60)

tag_drift = []
for col_fqn, expected_tag in expected_tags.items():
    parts = col_fqn.rsplit('.', 1)
    table_fqn = parts[0]
    col_name = parts[1]
    cat, sch, tbl = table_fqn.split('.')
    
    try:
        result = spark.sql(f"""
            SELECT tag_name FROM system.information_schema.column_tags
            WHERE catalog_name = '{cat}'
              AND schema_name = '{sch}'
              AND table_name = '{tbl}'
              AND column_name = '{col_name}'
              AND tag_name = '{expected_tag}'
        """).collect()
        
        if result:
            print(f"  \u2713 {col_fqn} has tag '{expected_tag}'")
        else:
            print(f"  \u2717 DRIFT: {col_fqn} MISSING tag '{expected_tag}'")
            tag_drift.append(col_fqn)
    except Exception as e:
        print(f"  \u26a0 ERROR checking {col_fqn}: {str(e)[:60]}")
        tag_drift.append(col_fqn)

# COMMAND ----------

# Check policy drift
print("\nChecking ABAC policies...")
print("=" * 60)

policy_drift = []
try:
    policies_df = spark.sql(f"SHOW POLICIES ON SCHEMA {catalog}.{schema}")
    active_policies = set(row['Policy Name'] for row in policies_df.collect())
    
    for expected in expected_policies:
        if expected in active_policies:
            print(f"  \u2713 Policy '{expected}' is active")
        else:
            print(f"  \u2717 DRIFT: Policy '{expected}' is MISSING")
            policy_drift.append(expected)
except Exception as e:
    print(f"  \u26a0 Could not check policies: {str(e)[:80]}")

# COMMAND ----------

# Summary
print(f"\n{'='*60}")
print("DRIFT DETECTION SUMMARY")
print(f"{'='*60}")
print(f"  Tag drift items:    {len(tag_drift)}")
print(f"  Policy drift items: {len(policy_drift)}")

if tag_drift or policy_drift:
    print(f"\n\u26a0 DRIFT DETECTED - Remediation required")
    if tag_drift:
        print(f"  Missing tags on: {tag_drift}")
    if policy_drift:
        print(f"  Missing policies: {policy_drift}")
else:
    print(f"\n\u2713 NO DRIFT - All governance controls are in place")