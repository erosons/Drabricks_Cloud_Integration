# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Setup Configuration
# Configuration - Adjust these to match your environment
UC_CATALOG = "eromonsei_catalog"
USER_SCHEMA_PREFIX = "samson_eromonsei"  # your schema prefix in Users catalog
SDP_META_SCHEMA = f"{USER_SCHEMA_PREFIX}_sdp_meta_specs"
BRONZE_SCHEMA = f"{USER_SCHEMA_PREFIX}_sdp_meta_bronze"
SILVER_SCHEMA = f"{USER_SCHEMA_PREFIX}_sdp_meta_silver"
VOLUME_NAME = "sdp_meta_files"
VOLUME_PATH = f"/Volumes/{UC_CATALOG}/{SDP_META_SCHEMA}/{VOLUME_NAME}"

print(f"Catalog: {UC_CATALOG}")
print(f"SDP Meta Schema: {SDP_META_SCHEMA}")
print(f"Bronze Schema: {BRONZE_SCHEMA}")
print(f"Silver Schema: {SILVER_SCHEMA}")
print(f"Volume Path: {VOLUME_PATH}")

# COMMAND ----------

# DBTITLE 1,Step 1: Create Schemas and Volume
# MAGIC %sql
# MAGIC -- Create all required schemas
# MAGIC CREATE SCHEMA IF NOT EXISTS ${UC_CATALOG}.${SDP_META_SCHEMA};
# MAGIC CREATE SCHEMA IF NOT EXISTS ${UC_CATALOG}.${BRONZE_SCHEMA};
# MAGIC CREATE SCHEMA IF NOT EXISTS ${UC_CATALOG}.${SILVER_SCHEMA};
# MAGIC
# MAGIC -- Create UC Volume for configs and test data
# MAGIC CREATE VOLUME IF NOT EXISTS ${UC_CATALOG}.${USER_SCHEMA_PREFIX}.${VOLUME_NAME};

# COMMAND ----------

# DBTITLE 1,Step 1b: Create schemas (Python fallback)
# Create all required schemas and volume
for schema in [SDP_META_SCHEMA, BRONZE_SCHEMA, SILVER_SCHEMA]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {UC_CATALOG}.{schema}")
    print(f"  Schema ready: {UC_CATALOG}.{schema}")

# Create UC Volume for configs and test data (in the SDP meta schema)
spark.sql(f"CREATE VOLUME IF NOT EXISTS {UC_CATALOG}.{SDP_META_SCHEMA}.{VOLUME_NAME}")
print(f"  Volume ready: /Volumes/{UC_CATALOG}/{SDP_META_SCHEMA}/{VOLUME_NAME}")
print("\nAll schemas and volume created successfully.")

# COMMAND ----------

# DBTITLE 1,Step 2: Create directory structure in Volume
import os

# Directory structure for the volume
dirs = [
    f"{VOLUME_PATH}/conf/ddl",
    f"{VOLUME_PATH}/conf/dqe/uc1_orders",
    f"{VOLUME_PATH}/conf/dqe/uc2_kafka",
    f"{VOLUME_PATH}/conf/dqe/uc3_eventhub",
    f"{VOLUME_PATH}/conf/dqe/uc8_append",
    f"{VOLUME_PATH}/test_data/uc1_cloudfiles/orders",
    f"{VOLUME_PATH}/test_data/uc4_snapshot/stores",
    f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_us",
    f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_eu",
    f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_apac",
    f"{VOLUME_PATH}/test_data/uc6_fanout/vehicles",
    f"{VOLUME_PATH}/test_data/uc7_row_filter/employees",
    f"{VOLUME_PATH}/test_data/uc8_append/payments_primary",
    f"{VOLUME_PATH}/test_data/uc8_append/payments_secondary",
    f"{VOLUME_PATH}/test_data/uc8_append/payments_tertiary",
    f"{VOLUME_PATH}/wheels",
]

for d in dirs:
    os.makedirs(d, exist_ok=True)
    print(f"Created: {d}")

print("\nDirectory structure created.")

# COMMAND ----------

# DBTITLE 1,Step 3: Generate DDL files for all use cases
# DDL files define the bronze table schema (all STRING for bronze layer)
ddl_files = {
    # UC1: Orders
    "orders.ddl": """order_id STRING, customer_id STRING, order_date STRING, amount STRING, status STRING, operation STRING, updated_at STRING""",
    
    # UC2: Kafka IoT Events
    "iot_events.ddl": """key STRING, value STRING, topic STRING, partition STRING, offset STRING, timestamp STRING, date STRING""",
    
    # UC3: EventHub Telemetry
    "eventhub_telemetry.ddl": """body STRING, partition STRING, offset STRING, sequenceNumber STRING, enqueuedTime STRING, publisher STRING""",
    
    # UC5: Multi-Source CDC - US
    "customers_us.ddl": """id STRING, firstname STRING, lastname STRING, email STRING, address STRING, operation STRING, operation_date STRING""",
    
    # UC5: Multi-Source CDC - EU
    "customers_eu.ddl": """customer_id STRING, given_name STRING, family_name STRING, email_address STRING, postal_address STRING, change_type STRING, change_ts STRING""",
    
    # UC5: Multi-Source CDC - APAC
    "customers_apac.ddl": """cust_id STRING, fname STRING, lname STRING, mail STRING, addr STRING, op STRING, op_time STRING""",
    
    # UC7: Employees
    "employees.ddl": """employee_id STRING, first_name STRING, last_name STRING, email STRING, department STRING, hire_date STRING, salary STRING""",
    
    # UC8: Payments
    "payments.ddl": """payment_id STRING, order_id STRING, customer_id STRING, amount STRING, payment_method STRING, payment_date STRING, status STRING""",
}

for filename, ddl_content in ddl_files.items():
    path = f"{VOLUME_PATH}/conf/ddl/{filename}"
    with open(path, "w") as f:
        f.write(ddl_content)
    print(f"Written: {path}")

print(f"\n{len(ddl_files)} DDL files created.")

# COMMAND ----------

# DBTITLE 1,Step 4: Generate DQE expectation files
import json

dqe_files = {
    # UC1: Orders - Bronze
    "dqe/uc1_orders/bronze_expectations.json": {
        "expect": {
            "valid_order_date": "order_date IS NOT NULL",
            "valid_amount": "amount IS NOT NULL"
        },
        "expect_or_drop": {
            "no_rescued_data": "_rescued_data IS NULL"
        },
        "expect_or_quarantine": {
            "quarantine_null_order_id": "order_id IS NULL OR customer_id IS NULL"
        }
    },
    # UC1: Orders - Silver
    "dqe/uc1_orders/silver_expectations.json": {
        "expect": {
            "valid_order_id": "order_id IS NOT NULL",
            "valid_customer_id": "customer_id IS NOT NULL",
            "valid_order_date": "order_date IS NOT NULL",
            "positive_amount": "amount > 0"
        }
    },
    # UC2: Kafka - Bronze
    "dqe/uc2_kafka/bronze_expectations.json": {
        "expect": {
            "valid_value": "value IS NOT NULL",
            "valid_timestamp": "timestamp IS NOT NULL"
        },
        "expect_or_quarantine": {
            "quarantine_null_key": "key IS NULL"
        }
    },
    # UC3: EventHub - Bronze
    "dqe/uc3_eventhub/bronze_expectations.json": {
        "expect": {
            "valid_body": "body IS NOT NULL",
            "valid_enqueuedTime": "enqueuedTime IS NOT NULL"
        },
        "expect_or_quarantine": {
            "quarantine_empty_body": "body IS NULL OR LENGTH(CAST(body AS STRING)) = 0"
        }
    },
    # UC8: Append Flows - Bronze
    "dqe/uc8_append/bronze_expectations.json": {
        "expect": {
            "valid_payment_id": "payment_id IS NOT NULL",
            "valid_amount": "amount IS NOT NULL"
        },
        "expect_or_drop": {
            "no_rescued_data": "_rescued_data IS NULL"
        }
    }
}

for filepath, content in dqe_files.items():
    full_path = f"{VOLUME_PATH}/conf/{filepath}"
    with open(full_path, "w") as f:
        json.dump(content, f, indent=2)
    print(f"Written: {full_path}")

print(f"\n{len(dqe_files)} DQE expectation files created.")

# COMMAND ----------

# DBTITLE 1,Step 5: Generate silver transformation files
silver_transformations = [
    {
        "target_table": "orders",
        "select_exp": [
            "order_id",
            "customer_id",
            "CAST(order_date AS DATE) AS order_date",
            "CAST(amount AS DECIMAL(10,2)) AS amount",
            "status",
            "operation",
            "updated_at",
            "_rescued_data"
        ],
        "where_clause": "order_id IS NOT NULL"
    },
    {
        "target_table": "products",
        "select_exp": [
            "product_id",
            "product_name",
            "CAST(price AS DECIMAL(10,2)) AS price",
            "category"
        ]
    },
    {
        "target_table": "stores",
        "select_exp": [
            "store_id",
            "store_name",
            "address",
            "city",
            "state"
        ]
    },
    {
        "target_table": "employees",
        "select_exp": [
            "employee_id",
            "CONCAT(first_name, ' ', last_name) AS full_name",
            "email",
            "department",
            "CAST(hire_date AS DATE) AS hire_date"
        ],
        "where_clause": "employee_id IS NOT NULL AND department IS NOT NULL"
    }
]

silver_transformations_fanout = [
    {"target_table": "vehicles_usa", "select_exp": ["*"], "where_clause": "country = 'USA'"},
    {"target_table": "vehicles_germany", "select_exp": ["*"], "where_clause": "country = 'Germany'"},
    {"target_table": "vehicles_japan", "select_exp": ["*"], "where_clause": "country = 'Japan'"}
]

# Write silver transformations
with open(f"{VOLUME_PATH}/conf/silver_transformations.json", "w") as f:
    json.dump(silver_transformations, f, indent=2)
print(f"Written: {VOLUME_PATH}/conf/silver_transformations.json")

with open(f"{VOLUME_PATH}/conf/silver_transformations_fanout.json", "w") as f:
    json.dump(silver_transformations_fanout, f, indent=2)
print(f"Written: {VOLUME_PATH}/conf/silver_transformations_fanout.json")

# COMMAND ----------

# DBTITLE 1,Step 6: Generate test data - UC1 CloudFiles (Orders CSV)
from pyspark.sql import functions as F
from pyspark.sql.types import *
import datetime

# UC1: Orders CSV data
orders_data = [
    ("ORD001", "CUST001", "2025-01-15", "150.50", "COMPLETED", "APPEND", "2025-01-15T10:00:00"),
    ("ORD002", "CUST002", "2025-01-16", "299.99", "PENDING", "APPEND", "2025-01-16T11:30:00"),
    ("ORD003", "CUST003", "2025-01-17", "75.00", "COMPLETED", "APPEND", "2025-01-17T09:15:00"),
    ("ORD004", "CUST001", "2025-01-18", "420.75", "SHIPPED", "APPEND", "2025-01-18T14:20:00"),
    ("ORD005", "CUST004", "2025-01-19", "89.99", "COMPLETED", "APPEND", "2025-01-19T16:45:00"),
    ("ORD006", "CUST002", "2025-01-20", "1250.00", "PENDING", "UPDATE", "2025-01-20T08:00:00"),
    ("ORD007", "CUST005", "2025-01-21", "55.25", "CANCELLED", "DELETE", "2025-01-21T12:30:00"),
    ("ORD008", None, "2025-01-22", "200.00", "PENDING", "APPEND", "2025-01-22T10:00:00"),  # quarantine: null customer
    ("ORD009", "CUST003", "2025-01-23", "330.50", "COMPLETED", "APPEND", "2025-01-23T17:00:00"),
    ("ORD010", "CUST006", "2025-01-24", "99.99", "SHIPPED", "APPEND", "2025-01-24T09:45:00"),
]

orders_schema = StructType([
    StructField("order_id", StringType()),
    StructField("customer_id", StringType()),
    StructField("order_date", StringType()),
    StructField("amount", StringType()),
    StructField("status", StringType()),
    StructField("operation", StringType()),
    StructField("updated_at", StringType()),
])

orders_df = spark.createDataFrame(orders_data, schema=orders_schema)
orders_df.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{VOLUME_PATH}/test_data/uc1_cloudfiles/orders")
print(f"UC1: Written {orders_df.count()} orders records")
orders_df.show(truncate=False)

# COMMAND ----------

# DBTITLE 1,Step 7: Generate test data - UC4 Snapshot (Stores CSV snapshots)
# UC4b: CSV file-based snapshots (versioned LOAD_1.csv, LOAD_2.csv, etc.)
stores_v1 = [
    ("STR001", "Downtown Store", "123 Main St", "New York", "NY"),
    ("STR002", "Mall Store", "456 Oak Ave", "Los Angeles", "CA"),
    ("STR003", "Airport Store", "789 Terminal Blvd", "Chicago", "IL"),
]

stores_v2 = [
    ("STR001", "Downtown Flagship", "123 Main St", "New York", "NY"),  # updated name
    ("STR002", "Mall Store", "456 Oak Ave", "Los Angeles", "CA"),
    ("STR003", "Airport Store", "789 Terminal Blvd", "Chicago", "IL"),
    ("STR004", "Suburban Store", "321 Elm Dr", "Houston", "TX"),  # new store
]

stores_schema = StructType([
    StructField("store_id", StringType()),
    StructField("store_name", StringType()),
    StructField("address", StringType()),
    StructField("city", StringType()),
    StructField("state", StringType()),
])

# Write snapshot version 1
df_v1 = spark.createDataFrame(stores_v1, schema=stores_schema)
df_v1.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{VOLUME_PATH}/test_data/uc4_snapshot/stores/LOAD_1.csv")

# Write snapshot version 2
df_v2 = spark.createDataFrame(stores_v2, schema=stores_schema)
df_v2.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{VOLUME_PATH}/test_data/uc4_snapshot/stores/LOAD_2.csv")

print(f"UC4: Written snapshot v1 ({df_v1.count()} rows) and v2 ({df_v2.count()} rows)")

# UC4a: Create source products Delta table for snapshot CDC
products_data = [
    ("PROD001", "Laptop Pro", "1299.99", "Electronics"),
    ("PROD002", "Wireless Mouse", "29.99", "Accessories"),
    ("PROD003", "USB-C Hub", "49.99", "Accessories"),
    ("PROD004", "Monitor 27in", "399.99", "Electronics"),
    ("PROD005", "Keyboard Mech", "89.99", "Accessories"),
]

products_schema = StructType([
    StructField("product_id", StringType()),
    StructField("product_name", StringType()),
    StructField("price", StringType()),
    StructField("category", StringType()),
])

products_df = spark.createDataFrame(products_data, schema=products_schema)
products_df.write.mode("overwrite").saveAsTable(f"{UC_CATALOG}.{BRONZE_SCHEMA}.source_products_snapshot")
print(f"UC4a: Written {products_df.count()} products to source Delta table")

# COMMAND ----------

# DBTITLE 1,Step 8: Generate test data - UC5 Multi-Source CDC (3 regions)
# UC5: Multi-Source CDC - US Region
us_data = [
    ("1001", "John", "Smith", "john.smith@email.com", "123 Broadway, NY", "APPEND", "2025-01-15T10:00:00"),
    ("1002", "Jane", "Doe", "jane.doe@email.com", "456 5th Ave, NY", "APPEND", "2025-01-16T11:00:00"),
    ("1003", "Bob", "Wilson", "bob.w@email.com", "789 Market St, SF", "UPDATE", "2025-01-17T12:00:00"),
]
us_schema = ["id", "firstname", "lastname", "email", "address", "operation", "operation_date"]
df_us = spark.createDataFrame(us_data, schema=us_schema)
df_us.coalesce(1).write.mode("overwrite").json(f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_us")
print(f"UC5: Written {df_us.count()} US customer CDC records")

# UC5: Multi-Source CDC - EU Region (different column names)
eu_data = [
    ("2001", "Hans", "Mueller", "hans.m@email.de", "10 Berliner Str, Berlin", "INSERT", "2025-01-15T09:00:00"),
    ("2002", "Marie", "Dupont", "marie.d@email.fr", "5 Rue de la Paix, Paris", "INSERT", "2025-01-16T10:00:00"),
    ("2003", "Paolo", "Rossi", "paolo.r@email.it", "3 Via Roma, Milan", "UPDATE", "2025-01-17T11:00:00"),
]
eu_schema = ["customer_id", "given_name", "family_name", "email_address", "postal_address", "change_type", "change_ts"]
df_eu = spark.createDataFrame(eu_data, schema=eu_schema)
df_eu.coalesce(1).write.mode("overwrite").json(f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_eu")
print(f"UC5: Written {df_eu.count()} EU customer CDC records")

# UC5: Multi-Source CDC - APAC Region (different column names)
apac_data = [
    ("3001", "Yuki", "Tanaka", "yuki.t@email.jp", "1-2-3 Shibuya, Tokyo", "I", "2025-01-15T08:00:00"),
    ("3002", "Wei", "Chen", "wei.c@email.cn", "88 Nanjing Rd, Shanghai", "I", "2025-01-16T09:00:00"),
    ("3003", "Raj", "Patel", "raj.p@email.in", "42 MG Road, Mumbai", "U", "2025-01-17T10:00:00"),
]
apac_schema = ["cust_id", "fname", "lname", "mail", "addr", "op", "op_time"]
df_apac = spark.createDataFrame(apac_data, schema=apac_schema)
df_apac.coalesce(1).write.mode("overwrite").json(f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_apac")
print(f"UC5: Written {df_apac.count()} APAC customer CDC records")

# COMMAND ----------

# DBTITLE 1,Step 9: Generate test data - UC6 Silver Fanout (Vehicles)
# UC6: Vehicles for fanout (USA, Germany, Japan filters)
vehicles_data = [
    ("V001", "Ford", "F-150", "2024", "USA", "45000"),
    ("V002", "Chevrolet", "Silverado", "2024", "USA", "42000"),
    ("V003", "BMW", "X5", "2024", "Germany", "65000"),
    ("V004", "Mercedes", "GLE", "2024", "Germany", "72000"),
    ("V005", "Toyota", "Camry", "2024", "Japan", "28000"),
    ("V006", "Honda", "Civic", "2024", "Japan", "25000"),
    ("V007", "Tesla", "Model 3", "2024", "USA", "38000"),
    ("V008", "Audi", "Q7", "2024", "Germany", "58000"),
    ("V009", "Nissan", "Altima", "2024", "Japan", "27000"),
    ("V010", "Dodge", "Ram", "2024", "USA", "48000"),
]
vehicles_schema = ["vehicle_id", "make", "model", "year", "country", "price"]
df_vehicles = spark.createDataFrame(vehicles_data, schema=vehicles_schema)
df_vehicles.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{VOLUME_PATH}/test_data/uc6_fanout/vehicles")
print(f"UC6: Written {df_vehicles.count()} vehicles (USA: 4, Germany: 3, Japan: 3)")
df_vehicles.groupBy("country").count().show()

# COMMAND ----------

# DBTITLE 1,Step 10: Generate test data - UC7 Row Filter (Employees)
# UC7: Employees with department-based row filter
employees_data = [
    ("EMP001", "Alice", "Johnson", "alice.j@company.com", "Engineering", "2020-03-15", "120000"),
    ("EMP002", "Bob", "Williams", "bob.w@company.com", "Engineering", "2021-06-01", "115000"),
    ("EMP003", "Carol", "Brown", "carol.b@company.com", "Finance", "2019-11-20", "105000"),
    ("EMP004", "David", "Lee", "david.l@company.com", "Finance", "2022-01-10", "98000"),
    ("EMP005", "Eve", "Garcia", "eve.g@company.com", "HR", "2020-08-25", "95000"),
    ("EMP006", "Frank", "Martinez", "frank.m@company.com", "HR", "2023-02-14", "88000"),
    ("EMP007", "Grace", "Taylor", "grace.t@company.com", "Engineering", "2021-09-30", "130000"),
    ("EMP008", "Henry", "Anderson", "henry.a@company.com", "Sales", "2022-04-18", "92000"),
]
employees_schema = ["employee_id", "first_name", "last_name", "email", "department", "hire_date", "salary"]
df_employees = spark.createDataFrame(employees_data, schema=employees_schema)
df_employees.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{VOLUME_PATH}/test_data/uc7_row_filter/employees")
print(f"UC7: Written {df_employees.count()} employees")
df_employees.groupBy("department").count().show()

# COMMAND ----------

# DBTITLE 1,Step 11: Generate test data - UC8 Append Flows (Payments)
# UC8: Payments from 3 different sources (primary, secondary, tertiary)
payments_primary = [
    ("PAY001", "ORD001", "CUST001", "150.50", "credit_card", "2025-01-15", "completed"),
    ("PAY002", "ORD002", "CUST002", "299.99", "debit_card", "2025-01-16", "completed"),
    ("PAY003", "ORD003", "CUST003", "75.00", "paypal", "2025-01-17", "completed"),
]

payments_secondary = [
    ("PAY004", "ORD004", "CUST001", "420.75", "credit_card", "2025-01-18", "completed"),
    ("PAY005", "ORD005", "CUST004", "89.99", "wire_transfer", "2025-01-19", "pending"),
]

payments_tertiary = [
    ("PAY006", "ORD006", "CUST002", "1250.00", "credit_card", "2025-01-20", "completed"),
    ("PAY007", "ORD009", "CUST003", "330.50", "debit_card", "2025-01-23", "completed"),
]

payments_schema = ["payment_id", "order_id", "customer_id", "amount", "payment_method", "payment_date", "status"]

for name, data in [("primary", payments_primary), ("secondary", payments_secondary), ("tertiary", payments_tertiary)]:
    df = spark.createDataFrame(data, schema=payments_schema)
    df.coalesce(1).write.mode("overwrite").json(f"{VOLUME_PATH}/test_data/uc8_append/payments_{name}")
    print(f"UC8: Written {df.count()} {name} payment records")

# COMMAND ----------

# DBTITLE 1,Step 12: Generate test data - UC9 Delta Source (Upstream Inventory)
# UC9: Create upstream inventory Delta table for table-to-table replication
inventory_data = [
    ("SKU001", "WH-EAST", 150, "2025-01-15"),
    ("SKU002", "WH-EAST", 300, "2025-01-15"),
    ("SKU003", "WH-WEST", 75, "2025-01-16"),
    ("SKU004", "WH-WEST", 200, "2025-01-16"),
    ("SKU001", "WH-CENTRAL", 500, "2025-01-17"),
    ("SKU005", "WH-EAST", 120, "2025-01-18"),
]

inventory_schema = StructType([
    StructField("sku", StringType()),
    StructField("warehouse_id", StringType()),
    StructField("quantity", IntegerType()),
    StructField("last_updated", StringType()),
])

df_inventory = spark.createDataFrame(inventory_data, schema=inventory_schema)
df_inventory.write.mode("overwrite").saveAsTable(f"{UC_CATALOG}.{BRONZE_SCHEMA}.upstream_inventory")

# Enable CDF for delta streaming replication
spark.sql(f"ALTER TABLE {UC_CATALOG}.{BRONZE_SCHEMA}.upstream_inventory SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
print(f"UC9: Written {df_inventory.count()} inventory records with CDF enabled")
df_inventory.show()

# COMMAND ----------

# DBTITLE 1,Step 13: Write master onboarding configuration to volume
# Write the master onboarding JSON to the volume
onboarding_config = [
    {
        "data_flow_id": "100",
        "data_flow_group": "uc1_cloudfiles",
        "source_system": "SFTP",
        "source_format": "cloudFiles",
        "source_details": {
            "source_database": "APP",
            "source_table": "ORDERS",
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc1_cloudfiles/orders",
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/orders.ddl",
            "source_metadata": {
                "include_autoloader_metadata_column": "True",
                "autoloader_metadata_col_name": "source_metadata",
                "select_metadata_cols": {
                    "input_file_name": "_metadata.file_name",
                    "input_file_path": "_metadata.file_path"
                }
            }
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "orders",
        "bronze_table_comment": "Orders bronze - raw CSV ingestion",
        "bronze_reader_options": {
            "cloudFiles.format": "csv",
            "cloudFiles.rescuedDataColumn": "_rescued_data",
            "header": "true",
            "cloudFiles.schemaEvolutionMode": "rescue"
        },
        "bronze_table_properties": {"pipelines.autoOptimize.managed": "true"},
        "bronze_cluster_by": ["order_id", "order_date"],
        "bronze_data_quality_expectations_json_dev": f"{VOLUME_PATH}/conf/dqe/uc1_orders/bronze_expectations.json",
        "bronze_catalog_quarantine_dev": UC_CATALOG,
        "bronze_database_quarantine_dev": BRONZE_SCHEMA,
        "bronze_quarantine_table": "orders_quarantine",
        "bronze_quarantine_table_properties": {"pipelines.reset.allowed": "false"},
        "bronze_quarantine_table_cluster_by": ["order_id"],
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "orders",
        "silver_table_comment": "Orders silver - CDC SCD Type 2",
        "silver_cdc_apply_changes": {
            "keys": ["order_id"],
            "sequence_by": "updated_at",
            "scd_type": "2",
            "apply_as_deletes": "operation = 'DELETE'",
            "except_column_list": ["operation", "updated_at", "_rescued_data"]
        },
        "silver_cluster_by": ["order_id", "customer_id"],
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations.json",
        "silver_data_quality_expectations_json_dev": f"{VOLUME_PATH}/conf/dqe/uc1_orders/silver_expectations.json"
    },
    {
        "data_flow_id": "200",
        "data_flow_group": "uc2_kafka",
        "source_system": "IoT_Sensors",
        "source_format": "kafka",
        "source_details": {
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/iot_events.ddl",
            "subscribe": "iot-sensor-events",
            "kafka.security.protocol": "SASL_SSL",
            "kafka.sasl.mechanism": "PLAIN",
            "kafka_source_servers_secrets_scope_name": "sdp_meta_kafka",
            "kafka_source_servers_secrets_scope_key": "bootstrap_servers"
        },
        "bronze_reader_options": {
            "startingOffsets": "earliest",
            "maxOffsetsPerTrigger": "50000",
            "failOnDataLoss": "false",
            "kafka.request.timeout.ms": "60000",
            "kafka.session.timeout.ms": "60000"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "iot_events",
        "bronze_data_quality_expectations_json_dev": f"{VOLUME_PATH}/conf/dqe/uc2_kafka/bronze_expectations.json",
        "bronze_catalog_quarantine_dev": UC_CATALOG,
        "bronze_database_quarantine_dev": BRONZE_SCHEMA,
        "bronze_quarantine_table": "iot_events_quarantine",
        "bronze_sinks": [
            {
                "name": "iot_events_kafka_sink",
                "format": "kafka",
                "options": {
                    "kafka_sink_servers_secret_scope_name": "sdp_meta_kafka",
                    "kafka_sink_servers_secret_scope_key": "sink_bootstrap_servers",
                    "kafka.security.protocol": "SASL_SSL",
                    "topic": "iot-events-processed"
                },
                "select_exp": ["value"],
                "where_clause": "value is not null"
            },
            {
                "name": "iot_events_delta_sink",
                "format": "delta",
                "options": {"path": f"/Volumes/{UC_CATALOG}/{BRONZE_SCHEMA}/sdp_meta_volume/data/sink/iot"},
                "select_exp": ["value"],
                "where_clause": "value is not null"
            }
        ]
    },
    {
        "data_flow_id": "300",
        "data_flow_group": "uc3_eventhub",
        "source_system": "Azure_IoT_Hub",
        "source_format": "eventhub",
        "source_details": {
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/eventhub_telemetry.ddl",
            "eventhub.accessKeyName": "listen-policy",
            "eventhub.name": "telemetry-hub",
            "eventhub.accessKeySecretName": "eh-access-key",
            "eventhub.secretsScopeName": "sdp_meta_eventhub",
            "kafka.sasl.mechanism": "PLAIN",
            "kafka.security.protocol": "SASL_SSL",
            "eventhub.namespace": "sdp-meta-test-ns",
            "eventhub.port": "9093"
        },
        "bronze_reader_options": {
            "maxOffsetsPerTrigger": "50000",
            "startingOffsets": "earliest",
            "failOnDataLoss": "false",
            "kafka.request.timeout.ms": "60000",
            "kafka.session.timeout.ms": "60000"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "telemetry_events",
        "bronze_data_quality_expectations_json_dev": f"{VOLUME_PATH}/conf/dqe/uc3_eventhub/bronze_expectations.json",
        "bronze_catalog_quarantine_dev": UC_CATALOG,
        "bronze_database_quarantine_dev": BRONZE_SCHEMA,
        "bronze_quarantine_table": "telemetry_events_quarantine",
        "bronze_append_flows": [
            {
                "name": "telemetry_bronze_append_flow",
                "create_streaming_table": False,
                "source_format": "eventhub",
                "source_details": {
                    "source_schema_path": f"{VOLUME_PATH}/conf/ddl/eventhub_telemetry.ddl",
                    "eventhub.accessKeyName": "listen-policy",
                    "eventhub.name": "telemetry-hub-overflow",
                    "eventhub.accessKeySecretName": "eh-access-key",
                    "eventhub.secretsScopeName": "sdp_meta_eventhub",
                    "kafka.sasl.mechanism": "PLAIN",
                    "kafka.security.protocol": "SASL_SSL",
                    "eventhub.namespace": "sdp-meta-test-ns",
                    "eventhub.port": "9093"
                },
                "reader_options": {
                    "maxOffsetsPerTrigger": "50000",
                    "startingOffsets": "earliest",
                    "failOnDataLoss": "false"
                },
                "once": False
            }
        ]
    },
    {
        "data_flow_id": "400",
        "data_flow_group": "uc4_snapshot",
        "source_system": "delta",
        "source_format": "snapshot",
        "source_details": {
            "snapshot_format": "delta",
            "source_catalog_dev": UC_CATALOG,
            "source_table": "source_products_snapshot",
            "source_database": f"{UC_CATALOG}.{BRONZE_SCHEMA}"
        },
        "bronze_database_dev": f"{UC_CATALOG}.{BRONZE_SCHEMA}",
        "bronze_table": "products_snapshot",
        "bronze_apply_changes_from_snapshot": {
            "keys": ["product_id"],
            "scd_type": "2"
        },
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "products",
        "silver_apply_changes_from_snapshot": {
            "keys": ["product_id"],
            "scd_type": "2"
        },
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations.json"
    },
    {
        "data_flow_id": "401",
        "data_flow_group": "uc4_snapshot",
        "source_system": "file_export",
        "source_format": "snapshot",
        "source_details": {
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc4_snapshot/stores/LOAD_",
            "snapshot_format": "csv"
        },
        "bronze_reader_options": {"header": "true"},
        "bronze_database_dev": f"{UC_CATALOG}.{BRONZE_SCHEMA}",
        "bronze_table": "stores_snapshot",
        "bronze_apply_changes_from_snapshot": {
            "keys": ["store_id"],
            "scd_type": "1"
        },
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "stores",
        "silver_apply_changes_from_snapshot": {
            "keys": ["store_id"],
            "scd_type": "1"
        },
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations.json"
    },
    {
        "data_flow_id": "500",
        "data_flow_group": "uc5_multi_cdc",
        "source_system": "RegionalCDC-US",
        "source_format": "cloudFiles",
        "source_details": {
            "source_database": "APP",
            "source_table": "CUSTOMERS_US",
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_us",
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/customers_us.ddl"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "customers_us_cdc",
        "bronze_reader_options": {
            "cloudFiles.format": "json",
            "cloudFiles.inferColumnTypes": "true",
            "cloudFiles.rescuedDataColumn": "_rescued_data"
        },
        "bronze_table_properties": {"pipelines.autoOptimize.managed": "true"}
    },
    {
        "data_flow_id": "501",
        "data_flow_group": "uc5_multi_cdc",
        "source_system": "RegionalCDC-EU",
        "source_format": "cloudFiles",
        "source_details": {
            "source_database": "APP",
            "source_table": "CUSTOMERS_EU",
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_eu",
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/customers_eu.ddl"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "customers_eu_cdc",
        "bronze_reader_options": {
            "cloudFiles.format": "json",
            "cloudFiles.inferColumnTypes": "true",
            "cloudFiles.rescuedDataColumn": "_rescued_data"
        }
    },
    {
        "data_flow_id": "502",
        "data_flow_group": "uc5_multi_cdc",
        "source_system": "RegionalCDC-APAC",
        "source_format": "cloudFiles",
        "source_details": {
            "source_database": "APP",
            "source_table": "CUSTOMERS_APAC",
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc5_multi_cdc/customers_apac",
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/customers_apac.ddl"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "customers_apac_cdc",
        "bronze_reader_options": {
            "cloudFiles.format": "json",
            "cloudFiles.inferColumnTypes": "true",
            "cloudFiles.rescuedDataColumn": "_rescued_data"
        },
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "customers_unified",
        "silver_table_properties": {"pipelines.reset.allowed": "false"},
        "silver_cdc_apply_changes_flows": {
            "keys": ["customer_id"],
            "sequence_by": "operation_date",
            "scd_type": "1",
            "apply_as_deletes": "operation = 'DELETE'",
            "except_column_list": ["operation", "operation_date", "_rescued_data"],
            "flows": [
                {
                    "name": "customers_us_silver",
                    "source_format": "delta",
                    "source_details": {
                        "source_catalog": UC_CATALOG,
                        "source_database": BRONZE_SCHEMA,
                        "source_table": "customers_us_cdc"
                    },
                    "select_exp": ["id AS customer_id", "firstname", "lastname", "email", "address", "'US' AS region", "operation", "operation_date", "_rescued_data"]
                },
                {
                    "name": "customers_eu_silver",
                    "source_format": "delta",
                    "source_details": {
                        "source_catalog": UC_CATALOG,
                        "source_database": BRONZE_SCHEMA,
                        "source_table": "customers_eu_cdc"
                    },
                    "select_exp": ["customer_id AS customer_id", "given_name AS firstname", "family_name AS lastname", "email_address AS email", "postal_address AS address", "'EU' AS region", "CASE WHEN change_type='INSERT' THEN 'APPEND' WHEN change_type='UPDATE' THEN 'UPDATE' WHEN change_type='DELETE' THEN 'DELETE' END AS operation", "change_ts AS operation_date", "_rescued_data"]
                },
                {
                    "name": "customers_apac_silver",
                    "source_format": "delta",
                    "source_details": {
                        "source_catalog": UC_CATALOG,
                        "source_database": BRONZE_SCHEMA,
                        "source_table": "customers_apac_cdc"
                    },
                    "select_exp": ["cust_id AS customer_id", "fname AS firstname", "lname AS lastname", "mail AS email", "addr AS address", "'APAC' AS region", "CASE WHEN op='I' THEN 'APPEND' WHEN op='U' THEN 'UPDATE' WHEN op='D' THEN 'DELETE' END AS operation", "op_time AS operation_date", "_rescued_data"]
                }
            ]
        }
    },
    {
        "data_flow_id": "600",
        "data_flow_group": "uc6_fanout",
        "source_system": "ERP",
        "source_format": "cloudFiles",
        "source_details": {
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc6_fanout/vehicles"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "vehicles",
        "bronze_reader_options": {
            "cloudFiles.format": "csv",
            "cloudFiles.rescuedDataColumn": "_rescued_data",
            "header": "true"
        },
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "vehicles_usa",
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations_fanout.json"
    },
    {
        "data_flow_id": "601",
        "data_flow_group": "uc6_fanout",
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "vehicles",
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "vehicles_germany",
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations_fanout.json"
    },
    {
        "data_flow_id": "602",
        "data_flow_group": "uc6_fanout",
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "vehicles",
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "vehicles_japan",
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations_fanout.json"
    },
    {
        "data_flow_id": "700",
        "data_flow_group": "uc7_row_filter",
        "source_system": "HR_System",
        "source_format": "cloudFiles",
        "source_details": {
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc7_row_filter/employees",
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/employees.ddl"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "employees",
        "bronze_reader_options": {
            "cloudFiles.format": "csv",
            "cloudFiles.rescuedDataColumn": "_rescued_data",
            "header": "true"
        },
        "bronze_cluster_by_auto": True,
        "bronze_row_filter": f"ROW FILTER {UC_CATALOG}.{BRONZE_SCHEMA}.department_filter ON (department)",
        "silver_catalog_dev": UC_CATALOG,
        "silver_database_dev": SILVER_SCHEMA,
        "silver_table": "employees",
        "silver_cluster_by_auto": True,
        "silver_transformation_json_dev": f"{VOLUME_PATH}/conf/silver_transformations.json",
        "silver_row_filter": f"ROW FILTER {UC_CATALOG}.{SILVER_SCHEMA}.department_filter ON (department)"
    },
    {
        "data_flow_id": "800",
        "data_flow_group": "uc8_append_flows",
        "source_system": "Payments",
        "source_format": "cloudFiles",
        "source_details": {
            "source_database": "APP",
            "source_table": "PAYMENTS",
            "source_path_dev": f"{VOLUME_PATH}/test_data/uc8_append/payments_primary",
            "source_schema_path": f"{VOLUME_PATH}/conf/ddl/payments.ddl"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "payments",
        "bronze_reader_options": {
            "cloudFiles.format": "json",
            "cloudFiles.inferColumnTypes": "true",
            "cloudFiles.rescuedDataColumn": "_rescued_data"
        },
        "bronze_append_flows": [
            {
                "name": "payments_secondary_flow",
                "create_streaming_table": False,
                "source_format": "cloudFiles",
                "source_details": {
                    "source_path_dev": f"{VOLUME_PATH}/test_data/uc8_append/payments_secondary",
                    "source_schema_path": f"{VOLUME_PATH}/conf/ddl/payments.ddl"
                },
                "reader_options": {
                    "cloudFiles.format": "json",
                    "cloudFiles.inferColumnTypes": "true",
                    "cloudFiles.rescuedDataColumn": "_rescued_data"
                },
                "once": False
            },
            {
                "name": "payments_tertiary_flow",
                "create_streaming_table": False,
                "source_format": "cloudFiles",
                "source_details": {
                    "source_path_dev": f"{VOLUME_PATH}/test_data/uc8_append/payments_tertiary",
                    "source_schema_path": f"{VOLUME_PATH}/conf/ddl/payments.ddl"
                },
                "reader_options": {
                    "cloudFiles.format": "json",
                    "cloudFiles.inferColumnTypes": "true",
                    "cloudFiles.rescuedDataColumn": "_rescued_data"
                },
                "once": False
            }
        ],
        "bronze_data_quality_expectations_json_dev": f"{VOLUME_PATH}/conf/dqe/uc8_append/bronze_expectations.json"
    },
    {
        "data_flow_id": "900",
        "data_flow_group": "uc9_delta",
        "source_system": "upstream_delta",
        "source_format": "delta",
        "source_details": {
            "source_database": f"{UC_CATALOG}.{BRONZE_SCHEMA}",
            "source_table": "upstream_inventory"
        },
        "bronze_catalog_dev": UC_CATALOG,
        "bronze_database_dev": BRONZE_SCHEMA,
        "bronze_table": "inventory_replica",
        "bronze_cluster_by": ["sku", "warehouse_id"]
    }
]

# Write to volume
onboarding_path = f"{VOLUME_PATH}/conf/onboarding_all_usecases.json"
with open(onboarding_path, "w") as f:
    json.dump(onboarding_config, f, indent=2)

print(f"Written master onboarding config: {onboarding_path}")
print(f"Total flows configured: {len(onboarding_config)}")

# COMMAND ----------

# DBTITLE 1,Step 14: Create Row Filter UDF for UC7
# UC7: Create the row filter function used by the row_filter use case
# This function restricts access based on department
try:
    spark.sql(f"""
    CREATE OR REPLACE FUNCTION {UC_CATALOG}.{BRONZE_SCHEMA}.department_filter(department STRING)
    RETURNS BOOLEAN
    RETURN IF(IS_ACCOUNT_GROUP_MEMBER('admin_group'), true, department = current_user())
    """)
    print(f"Created row filter UDF: {UC_CATALOG}.{BRONZE_SCHEMA}.department_filter")
except Exception as e:
    print(f"Note: Could not create row filter UDF (may need elevated permissions): {e}")
    print("UC7 Row Filter will need the UDF created manually before pipeline execution.")

try:
    spark.sql(f"""
    CREATE OR REPLACE FUNCTION {UC_CATALOG}.{SILVER_SCHEMA}.department_filter(department STRING)
    RETURNS BOOLEAN
    RETURN IF(IS_ACCOUNT_GROUP_MEMBER('admin_group'), true, department = current_user())
    """)
    print(f"Created row filter UDF: {UC_CATALOG}.{SILVER_SCHEMA}.department_filter")
except Exception as e:
    print(f"Note: Could not create silver row filter UDF: {e}")

# COMMAND ----------

# DBTITLE 1,Step 15: Validation Summary
import os

print("=" * 70)
print("SDP-META TEST USE CASES - SETUP COMPLETE")
print("=" * 70)
print()
print("INFRASTRUCTURE:")
print(f"  Catalog:      {UC_CATALOG}")
print(f"  Specs Schema: {UC_CATALOG}.{SDP_META_SCHEMA}")
print(f"  Bronze:       {UC_CATALOG}.{BRONZE_SCHEMA}")
print(f"  Silver:       {UC_CATALOG}.{SILVER_SCHEMA}")
print(f"  Volume:       {VOLUME_PATH}")
print()
print("USE CASES CONFIGURED:")
print("  UC1: CloudFiles CSV     -> DQE + quarantine + SCD Type 2 CDC")
print("  UC2: Kafka + Sinks      -> Dual sinks (Kafka + Delta)")
print("  UC3: EventHub           -> append_flows for multi-topic merge")
print("  UC4: Snapshot CDC       -> apply_changes_from_snapshot, SCD 1 & 2")
print("  UC5: Multi-Source CDC   -> 3 regions -> 1 unified silver table")
print("  UC6: Silver Fanout      -> 1 bronze -> 3 filtered silver tables")
print("  UC7: Row Filters        -> UC ROW FILTER row-level security")
print("  UC8: Append Flows       -> 3 sources merged into 1 streaming table")
print("  UC9: Delta Source       -> Table-to-table streaming replication")
print()
print("NEXT STEPS:")
print("  1. Upload sdp-meta wheel to:")
print(f"     {VOLUME_PATH}/wheels/")
print("  2. Deploy the bundle:")
print("     databricks bundle deploy --target dev")
print("  3. Run onboarding (loads specs):")
print("     databricks bundle run onboarding --target dev")
print("  4. Run pipelines:")
print("     databricks bundle run pipelines --target dev")
print()
print("NOTES:")
print("  - UC2 (Kafka) and UC3 (EventHub) require secret scopes to be configured")
print("  - UC7 (Row Filter) requires the department_filter UDF to exist")
print("  - UC4 (Snapshot) uses a custom runner notebook with callbacks")
print("=" * 70)

# Verify volume contents
print("\nVOLUME CONTENTS:")
for root, dirs, files in os.walk(VOLUME_PATH):
    level = root.replace(VOLUME_PATH, '').count(os.sep)
    indent = ' ' * 2 * level
    print(f"{indent}{os.path.basename(root)}/")
    subindent = ' ' * 2 * (level + 1)
    for file in files:
        print(f"{subindent}{file}")