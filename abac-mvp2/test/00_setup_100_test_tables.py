# Databricks notebook source
# DBTITLE 1,Test Setup: Create 100 Synthetic PII Tables
"""
Test Setup: Create 100 Synthetic Tables for ABAC MVP2 Testing

Creates tables distributed across 3 schemas to exercise:
- Auto-discovery (01b_auto_discover_tables)
- Template pattern matching (02_apply_governed_tags)
- Parallel policy creation (04_create_abac_policies)
- Drift detection (06_drift_detection)

Distribution:
  - 50 tables in customer schema  (standard_pii_table template)
  - 30 tables in finance schema   (financial_table template)
  - 20 tables in hr schema        (sensitive_hr_table template)

Each table has randomized columns that match template column_patterns
so the framework can auto-assign governed tags.
"""
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed

dbutils.widgets.text("catalog", "general_use", "Target Catalog")
dbutils.widgets.text("drop_existing", "true", "Drop existing test tables")

catalog = dbutils.widgets.get("catalog")
drop_existing = dbutils.widgets.get("drop_existing").lower() == "true"

print(f"Target catalog: {catalog}")
print(f"Drop existing: {drop_existing}")

# COMMAND ----------

# DBTITLE 1,Define table schemas per domain
# ============================================================================
# COLUMN POOLS: Columns that match template patterns for auto-tagging
# ============================================================================

# Columns for standard_pii_table template
CUSTOMER_COLUMNS = {
    "always": [
        ("customer_id", "BIGINT"),
        ("created_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
    ],
    "pii_pool": [
        # These match template column_patterns
        ("email", "STRING"),
        ("email_address", "STRING"),
        ("contact_email", "STRING"),
        ("phone_number", "STRING"),
        ("mobile", "STRING"),
        ("contact_phone", "STRING"),
        ("first_name", "STRING"),
        ("last_name", "STRING"),
        ("full_name", "STRING"),
        ("date_of_birth", "DATE"),
        ("ssn", "STRING"),
        ("street_address", "STRING"),
        ("postal_code", "STRING"),
        ("ip_address", "STRING"),
    ],
    "non_pii_pool": [
        ("account_status", "STRING"),
        ("region_code", "STRING"),
        ("signup_source", "STRING"),
        ("loyalty_tier", "STRING"),
        ("total_orders", "INT"),
        ("last_login", "TIMESTAMP"),
        ("preferred_language", "STRING"),
        ("country_code", "STRING"),
        ("is_active", "BOOLEAN"),
    ],
}

# Columns for financial_table template
FINANCE_COLUMNS = {
    "always": [
        ("transaction_id", "BIGINT"),
        ("transaction_date", "TIMESTAMP"),
        ("amount", "DOUBLE"),
        ("currency", "STRING"),
    ],
    "pii_pool": [
        ("email", "STRING"),
        ("credit_card", "STRING"),
        ("card_number", "STRING"),
        ("account_number", "STRING"),
        ("iban", "STRING"),
        ("cardholder_name", "STRING"),
        ("full_name", "STRING"),
    ],
    "non_pii_pool": [
        ("merchant_name", "STRING"),
        ("merchant_category", "STRING"),
        ("transaction_type", "STRING"),
        ("status", "STRING"),
        ("channel", "STRING"),
        ("risk_score", "DOUBLE"),
        ("is_fraud", "BOOLEAN"),
    ],
}

# Columns for sensitive_hr_table template
HR_COLUMNS = {
    "always": [
        ("employee_id", "BIGINT"),
        ("hire_date", "DATE"),
        ("is_active", "BOOLEAN"),
    ],
    "pii_pool": [
        ("email", "STRING"),
        ("work_email", "STRING"),
        ("phone_number", "STRING"),
        ("work_phone", "STRING"),
        ("ssn", "STRING"),
        ("date_of_birth", "DATE"),
        ("full_name", "STRING"),
        ("first_name", "STRING"),
        ("last_name", "STRING"),
        ("employee_name", "STRING"),
    ],
    "non_pii_pool": [
        ("department", "STRING"),
        ("salary", "DOUBLE"),
        ("compensation", "DOUBLE"),
        ("bonus", "DOUBLE"),
        ("job_title", "STRING"),
        ("manager_id", "BIGINT"),
        ("office_location", "STRING"),
        ("employment_type", "STRING"),
        ("performance_rating", "DOUBLE"),
    ],
}

print("Column pools defined:")
print(f"  Customer: {len(CUSTOMER_COLUMNS['pii_pool'])} PII + {len(CUSTOMER_COLUMNS['non_pii_pool'])} non-PII")
print(f"  Finance:  {len(FINANCE_COLUMNS['pii_pool'])} PII + {len(FINANCE_COLUMNS['non_pii_pool'])} non-PII")
print(f"  HR:       {len(HR_COLUMNS['pii_pool'])} PII + {len(HR_COLUMNS['non_pii_pool'])} non-PII")

# COMMAND ----------

# DBTITLE 1,Define table generation logic
def generate_table_spec(schema, table_name, column_pool, num_pii=3, num_non_pii=3):
    """
    Generate a table spec with randomized columns from the pool.
    Ensures each table has a mix of PII and non-PII columns.
    """
    columns = list(column_pool["always"])
    
    # Pick random PII columns
    pii_sample = random.sample(
        column_pool["pii_pool"],
        min(num_pii, len(column_pool["pii_pool"]))
    )
    columns.extend(pii_sample)
    
    # Pick random non-PII columns
    non_pii_sample = random.sample(
        column_pool["non_pii_pool"],
        min(num_non_pii, len(column_pool["non_pii_pool"]))
    )
    columns.extend(non_pii_sample)
    
    return {
        "schema": schema,
        "table_name": table_name,
        "columns": columns,
    }


def generate_sample_data_sql(fqn, columns, num_rows=10):
    """
    Generate INSERT statements with synthetic PII-like data.
    """
    domains = ["example.com", "company.co.uk", "enterprise.de", "mail.com", "corp.jp"]
    regions = ["us", "eu", "apac", "latam"]
    departments = ["engineering", "sales", "marketing", "hr", "finance"]
    
    rows = []
    for i in range(num_rows):
        values = []
        for col_name, col_type in columns:
            if col_type == "BIGINT":
                values.append(str(1000 + i))
            elif col_type == "INT":
                values.append(str(random.randint(0, 100)))
            elif col_type == "DOUBLE":
                values.append(f"{random.uniform(100, 100000):.2f}")
            elif col_type == "BOOLEAN":
                values.append(random.choice(["true", "false"]))
            elif col_type == "DATE":
                year = random.randint(1970, 2000)
                month = random.randint(1, 12)
                day = random.randint(1, 28)
                values.append(f"'{year}-{month:02d}-{day:02d}'")
            elif col_type == "TIMESTAMP":
                values.append("current_timestamp()")
            elif "email" in col_name:
                name = ''.join(random.choices(string.ascii_lowercase, k=6))
                values.append(f"'{name}@{random.choice(domains)}'")
            elif "phone" in col_name or "mobile" in col_name:
                values.append(f"'+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}'")
            elif "ssn" in col_name or "social_security" in col_name:
                values.append(f"'{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}'")
            elif "credit_card" in col_name or "card_number" in col_name:
                values.append(f"'4{random.randint(100,999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}'")
            elif "iban" in col_name:
                values.append(f"'GB{random.randint(10,99)}BARC{random.randint(10000000,99999999)}{random.randint(10000000,99999999)}'")
            elif "name" in col_name:
                names = ["Alice", "Bob", "Carol", "Dave", "Erin", "Frank", "Grace", "Henry", "Iris", "Jack"]
                values.append(f"'{random.choice(names)} {random.choice(string.ascii_uppercase)}.'") 
            elif "department" in col_name or "dept" in col_name:
                values.append(f"'{random.choice(departments)}'")
            elif "region" in col_name or "country" in col_name:
                values.append(f"'{random.choice(regions)}'")
            elif "ip_address" in col_name:
                values.append(f"'{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,255)}'")
            elif "address" in col_name or "postal" in col_name or "zip" in col_name:
                values.append(f"'{random.randint(100,999)} Main St, Suite {random.randint(1,500)}'")
            elif "salary" in col_name or "compensation" in col_name or "bonus" in col_name:
                values.append(f"{random.uniform(40000, 250000):.2f}")
            else:
                values.append(f"'val_{random.randint(1,1000)}'")
        rows.append(f"({', '.join(values)})")
    
    col_names = ", ".join(f"`{c[0]}`" for c in columns)
    return f"INSERT INTO {fqn} ({col_names}) VALUES\n" + ",\n".join(rows)


print("\u2713 Table generation functions defined")

# COMMAND ----------

# DBTITLE 1,Create schemas and generate 100 tables
# Ensure schemas exist
schemas_to_create = ["customer", "finance", "hr"]
for schema in schemas_to_create:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    print(f"\u2713 Schema ready: {catalog}.{schema}")

# Generate table specifications
random.seed(42)  # Reproducible
table_specs = []

# 50 customer tables
customer_table_names = [
    "customer_profile", "customer_addresses", "customer_preferences",
    "customer_sessions", "customer_devices", "customer_support_tickets",
    "customer_feedback", "customer_orders", "customer_returns",
    "customer_subscriptions", "customer_payments", "customer_loyalty",
    "customer_referrals", "customer_communications", "customer_segments",
    "customer_risk_scores", "customer_verification", "customer_consents",
    "customer_onboarding", "customer_churn_scores", "customer_ltv",
    "customer_interactions", "customer_campaigns", "customer_surveys",
    "customer_nps_scores", "customer_demographics", "customer_locations",
    "customer_preferences_v2", "customer_activity_log", "customer_milestones",
    "customer_rewards", "customer_tiers", "customer_vouchers",
    "customer_wishlist", "customer_cart_history", "customer_reviews",
    "customer_ratings", "customer_bookmarks", "customer_notifications",
    "customer_alerts", "customer_gdpr_requests", "customer_data_exports",
    "customer_identity_verification", "customer_kyc", "customer_aml_checks",
    "customer_credit_scores", "customer_income_verification",
    "customer_employment", "customer_social_profiles", "customer_marketing_consent",
]
for name in customer_table_names:
    spec = generate_table_spec("customer", name, CUSTOMER_COLUMNS,
                                num_pii=random.randint(2, 5),
                                num_non_pii=random.randint(2, 4))
    table_specs.append(spec)

# 30 finance tables
finance_table_names = [
    "transactions", "payments", "refunds", "settlements",
    "invoices", "billing_events", "subscription_charges",
    "wire_transfers", "ach_payments", "card_authorizations",
    "chargebacks", "disputes", "fee_schedules",
    "revenue_recognition", "deferred_revenue", "accounts_receivable",
    "accounts_payable", "general_ledger", "journal_entries",
    "bank_reconciliation", "cash_flow", "budget_actuals",
    "expense_reports", "vendor_payments", "payroll_disbursements",
    "tax_withholdings", "audit_trail", "compliance_transactions",
    "fraud_alerts", "risk_assessments",
]
for name in finance_table_names:
    spec = generate_table_spec("finance", name, FINANCE_COLUMNS,
                                num_pii=random.randint(2, 4),
                                num_non_pii=random.randint(2, 4))
    table_specs.append(spec)

# 20 HR tables
hr_table_names = [
    "employee_records", "employee_compensation", "employee_benefits",
    "employee_reviews", "employee_training", "employee_certifications",
    "employee_leave", "employee_attendance", "employee_expenses",
    "employee_relocations", "employee_promotions", "employee_terminations",
    "employee_onboarding", "employee_offboarding", "employee_surveys",
    "employee_engagement", "employee_goals", "employee_feedback",
    "employee_incidents", "employee_investigations",
]
for name in hr_table_names:
    spec = generate_table_spec("hr", name, HR_COLUMNS,
                                num_pii=random.randint(3, 5),
                                num_non_pii=random.randint(2, 4))
    table_specs.append(spec)

print(f"\nGenerated {len(table_specs)} table specifications:")
print(f"  Customer: {len(customer_table_names)}")
print(f"  Finance:  {len(finance_table_names)}")
print(f"  HR:       {len(hr_table_names)}")

# COMMAND ----------

# DBTITLE 1,Create tables in parallel
def create_table(spec):
    """
    Create a single table with synthetic data.
    Returns (status, fqn, error)
    """
    fqn = f"{catalog}.{spec['schema']}.{spec['table_name']}"
    columns = spec["columns"]
    
    try:
        # Drop if exists
        if drop_existing:
            spark.sql(f"DROP TABLE IF EXISTS {fqn}")
        
        # Build CREATE TABLE
        col_defs = ", ".join(f"`{name}` {dtype}" for name, dtype in columns)
        create_sql = f"CREATE TABLE IF NOT EXISTS {fqn} ({col_defs})"
        spark.sql(create_sql)
        
        # Insert sample data
        insert_sql = generate_sample_data_sql(fqn, columns, num_rows=10)
        spark.sql(insert_sql)
        
        return ("success", fqn, None)
    except Exception as e:
        return ("failed", fqn, str(e)[:200])


# Execute in parallel (20 workers)
created = []
failed = []

print(f"\nCreating {len(table_specs)} tables (20 parallel workers)...")
print("=" * 60)

with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(create_table, spec): spec for spec in table_specs}
    for i, future in enumerate(as_completed(futures), 1):
        status, fqn, error = future.result()
        if status == "success":
            created.append(fqn)
            if i % 10 == 0 or i == len(table_specs):
                print(f"  Progress: {i}/{len(table_specs)} tables created...")
        else:
            failed.append((fqn, error))
            print(f"  \u2717 {fqn}: {error[:80]}")

print(f"\n{'=' * 60}")
print(f"TEST DATA SETUP COMPLETE")
print(f"{'=' * 60}")
print(f"  Created: {len(created)}")
print(f"  Failed:  {len(failed)}")
print(f"  Schemas: {', '.join(f'{catalog}.{s}' for s in schemas_to_create)}")

if failed:
    print(f"\n\u2717 Failures:")
    for fqn, err in failed[:5]:
        print(f"    - {fqn}: {err}")

# COMMAND ----------

# DBTITLE 1,Verify table creation
# Verify tables exist in information_schema
print("\nVerification:")
print("=" * 60)

for schema in schemas_to_create:
    count_df = spark.sql(f"""
        SELECT COUNT(*) as table_count
        FROM {catalog}.information_schema.tables
        WHERE table_schema = '{schema}'
          AND table_type IN ('MANAGED', 'EXTERNAL')
    """)
    count = count_df.collect()[0].table_count
    print(f"  {catalog}.{schema}: {count} tables")

# Show sample of columns to verify PII pattern matching will work
print(f"\nSample columns from {catalog}.customer.customer_profile:")
cols_df = spark.sql(f"""
    SELECT column_name, data_type
    FROM {catalog}.information_schema.columns
    WHERE table_schema = 'customer'
      AND table_name = 'customer_profile'
    ORDER BY ordinal_position
""")
for row in cols_df.collect():
    print(f"  {row.column_name:25s} {row.data_type}")

print(f"\n\u2713 Test environment ready for auto-discovery and governance deployment.")
print(f"  Run the main orchestrator to apply policies to all {len(created)} tables.")

dbutils.notebook.exit(f"created={len(created)}, failed={len(failed)}")