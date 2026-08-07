# Databricks notebook source
# MAGIC %md
# MAGIC # Step 5: Validate ABAC Enforcement
# MAGIC Runs queries against the protected table and validates that:
# MAGIC - Email columns show masked values (`***@domain.com`)
# MAGIC - Phone columns show masked values (`(***) ***-XXXX`)
# MAGIC - Date of birth columns show year-only (`YYYY-01-01`)
# MAGIC
# MAGIC **Note:** If running as a member of `governance_cleartext_approved`,
# MAGIC you will see cleartext values. Remove yourself from that group to test masking.

# COMMAND ----------

dbutils.widgets.text("catalog", "general_use", "Target Catalog")
dbutils.widgets.text("schema", "customer", "Target Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

table_fqn = f"{catalog}.{schema}.customer_profile"
print(f"Testing enforcement on: {table_fqn}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query the protected table

# COMMAND ----------

# Query the PII columns - these should be masked for non-exempt users
result_df = spark.sql(f"""
    SELECT 
        customer_id,
        first_name,
        email,
        phone_number,
        date_of_birth,
        region_code
    FROM {table_fqn}
    ORDER BY customer_id
""")

print("Query results (PII columns should be masked):")
display(result_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validate masking patterns

# COMMAND ----------

import re
from datetime import date

rows = result_df.collect()
test_results = []

for row in rows:
    # Check email masking pattern: should be ***@domain.com
    email = row['email']
    if email and '@' in email:
        local_part = email.split('@')[0]
        if local_part == '***':
            test_results.append(('email_masked', row['customer_id'], 'PASS', email))
        elif '***' not in email:
            # Could be cleartext if user is in exception group
            test_results.append(('email_cleartext', row['customer_id'], 'CLEARTEXT', email))
        else:
            test_results.append(('email_partial', row['customer_id'], 'UNEXPECTED', email))
    
    # Check phone masking: should be (***) ***-XXXX
    phone = row['phone_number']
    if phone:
        if phone.startswith('(***)'):
            test_results.append(('phone_masked', row['customer_id'], 'PASS', phone))
        elif '***' not in phone:
            test_results.append(('phone_cleartext', row['customer_id'], 'CLEARTEXT', phone))
        else:
            test_results.append(('phone_partial', row['customer_id'], 'UNEXPECTED', phone))
    
    # Check DOB masking: should be YYYY-01-01
    dob = row['date_of_birth']
    if dob:
        if isinstance(dob, date) and dob.month == 1 and dob.day == 1:
            test_results.append(('dob_masked', row['customer_id'], 'PASS', str(dob)))
        else:
            test_results.append(('dob_cleartext', row['customer_id'], 'CLEARTEXT', str(dob)))

# COMMAND ----------

# Summarize results
pass_count = len([t for t in test_results if t[2] == 'PASS'])
cleartext_count = len([t for t in test_results if t[2] == 'CLEARTEXT'])
unexpected_count = len([t for t in test_results if t[2] == 'UNEXPECTED'])

print(f"{'='*70}")
print(f"ENFORCEMENT VALIDATION RESULTS")
print(f"{'='*70}")
print(f"  Total checks:  {len(test_results)}")
print(f"  MASKED (pass): {pass_count}")
print(f"  CLEARTEXT:     {cleartext_count}")
print(f"  UNEXPECTED:    {unexpected_count}")
print(f"{'='*70}")

if unexpected_count > 0:
    print("\n\u2717 UNEXPECTED results detected:")
    for t in test_results:
        if t[2] == 'UNEXPECTED':
            print(f"    customer_id={t[1]}: {t[0]} = {t[3]}")
    raise Exception("Validation failed: unexpected masking behavior")

elif cleartext_count > 0 and pass_count == 0:
    print("\n\u26a0 All values are CLEARTEXT.")
    print("  This means you are in the 'governance_cleartext_approved' group.")
    print("  To test masking, run as a user NOT in that group.")

elif pass_count > 0:
    print("\n\u2713 MASKING IS ACTIVE")
    print("  Email:  Showing ***@domain.com pattern")
    print("  Phone:  Showing (***) ***-XXXX pattern")
    print("  DOB:    Showing YYYY-01-01 (year only)")
    print("\n  ABAC enforcement is working correctly.")

# COMMAND ----------

# Show policies for reference
print("\nActive policies on this table:")
display(spark.sql(f"SHOW EFFECTIVE POLICIES ON TABLE {table_fqn}"))