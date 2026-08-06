# Databricks notebook source
# MAGIC %md
# MAGIC # Step 1: Setup Test Data
# MAGIC Creates synthetic test datasets with PII columns (DOB, email, phone)
# MAGIC for validating the ABAC masking framework.

# COMMAND ----------

dbutils.widgets.text("catalog", "general_use", "Target Catalog")
dbutils.widgets.text("schema", "customer", "Target Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Target: {catalog}.{schema}")

# COMMAND ----------

# Create catalog and schema if they don't exist
spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"USE SCHEMA {schema}")

print(f"\u2713 Catalog and schema ready: {catalog}.{schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create customer_profile table with PII columns

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE {catalog}.{schema}.customer_profile (
  customer_id BIGINT COMMENT 'Unique customer identifier',
  first_name STRING COMMENT 'Customer first name',
  last_name STRING COMMENT 'Customer last name',
  email STRING COMMENT 'Customer email address - PII',
  phone_number STRING COMMENT 'Customer phone number - PII',
  date_of_birth DATE COMMENT 'Customer date of birth - PII',
  ssn STRING COMMENT 'Social Security Number - PII',
  region_code STRING COMMENT 'Geographic region code',
  account_status STRING COMMENT 'Active or inactive',
  created_at TIMESTAMP COMMENT 'Record creation timestamp'
)
COMMENT 'Core customer profile with PII fields for ABAC testing'
""")

print("\u2713 Table created: customer_profile")

# COMMAND ----------

# Insert synthetic test data
spark.sql(f"""
INSERT OVERWRITE {catalog}.{schema}.customer_profile VALUES
  (1001, 'Alice', 'Johnson', 'alice.johnson@example.com', '+1-555-0101', '1985-03-15', '123-45-6789', 'us', 'active', current_timestamp()),
  (1002, 'Bob', 'Smith', 'bob.smith@company.co.uk', '+44-20-7946-0958', '1990-07-22', '234-56-7890', 'eu', 'active', current_timestamp()),
  (1003, 'Carol', 'Williams', 'carol.w@enterprise.de', '+49-30-1234-5678', '1978-11-08', '345-67-8901', 'eu', 'active', current_timestamp()),
  (1004, 'Dave', 'Brown', 'dave.brown@mail.com', '+1-555-0204', '1995-01-30', '456-78-9012', 'us', 'inactive', current_timestamp()),
  (1005, 'Erin', 'Davis', 'erin.davis@corp.jp', '+81-3-1234-5678', '1988-06-12', '567-89-0123', 'apac', 'active', current_timestamp()),
  (1006, 'Frank', 'Miller', 'frank.m@startup.io', '+1-555-0306', '1992-09-25', '678-90-1234', 'us', 'active', current_timestamp()),
  (1007, 'Grace', 'Wilson', 'grace.wilson@bank.sg', '+65-6123-4567', '1983-12-03', '789-01-2345', 'apac', 'active', current_timestamp()),
  (1008, 'Henry', 'Taylor', 'henry.t@fin.eu', '+33-1-2345-6789', '1975-04-18', '890-12-3456', 'eu', 'inactive', current_timestamp()),
  (1009, 'Iris', 'Anderson', 'iris.a@health.au', '+61-2-1234-5678', '1998-08-07', '901-23-4567', 'apac', 'active', current_timestamp()),
  (1010, 'Jack', 'Thomas', 'jack.thomas@gov.ca', '+1-613-555-0110', '1980-02-28', '012-34-5678', 'us', 'active', current_timestamp())
""")

print("\u2713 Inserted 10 test records")

# COMMAND ----------

# Verify the data
display(spark.sql(f"SELECT * FROM {catalog}.{schema}.customer_profile"))

# COMMAND ----------

print(f"""
{'='*60}
TEST DATA SETUP COMPLETE
{'='*60}
Table: {catalog}.{schema}.customer_profile
Rows:  10

PII Columns requiring governed tags:
  - email          -> class.email_address
  - phone_number   -> class.phone_number  
  - date_of_birth  -> class.date_of_birth
  - ssn            -> class.us_ssn
{'='*60}
""")
