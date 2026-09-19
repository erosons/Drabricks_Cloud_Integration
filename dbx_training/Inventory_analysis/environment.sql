"""
Unity Catalog Inventory Tool (Databricks)
----------------------------------------
A single-notebook Python utility to snapshot Unity Catalog assets and
permissions into Delta tables for reporting & audits.

Designed to run *inside* Databricks with default workspace auth via `databricks-sdk`.

What you get
- Snapshot Delta tables of: catalogs, schemas, tables, views, columns,
  functions, volumes, external locations, storage credentials, shares,
  providers, recipients, **table_privileges**, **schema_privileges**.
- Simple gold views for dashboarding (object counts, orphan schemata, top schemas).
- Idempotent writes (overwrite by `snapshot_date`) so you can schedule this job daily.

How to run
1) On a cluster or SQL Warehouse with Python:
   %pip install databricks-sdk pandas
2) Set the TARGET UC path below (catalog.schema) you have write access to.
3) Run all cells. Optionally schedule as a Job.

Notes
- Uses `system.information_schema` where possible for speed and stability.
- Falls back to `databricks-sdk` Unity Catalog APIs for items not in I_S (e.g., external locations, volumes).
- For very large estates, you can limit catalogs via `CATALOG_ALLOWLIST`.
"""

# COMMAND ----------
# %pip install databricks-sdk pandas

# COMMAND ----------
from __future__ import annotations
from datetime import datetime
from typing import List

import pandas as pd
from databricks.sdk import WorkspaceClient
from pyspark.sql import functions as F

# ==== CONFIG ====
# Where to write snapshot tables (must exist and be UC-enabled).
TARGET_CATALOG = "governance"
TARGET_SCHEMA = "inventory"
SNAPSHOT_DATE = datetime.utcnow().strftime("%Y-%m-%d")  # used to partition all tables

# Optional: restrict to a subset of catalogs. Empty list means: all catalogs.
CATALOG_ALLOWLIST: List[str] = []  # e.g., ["main", "prod", "sandbox"]

# Table name prefix; change if you want multiple runs side-by-side.
PREFIX = "ucinv_"

spark.sql(f"CREATE CATALOG IF NOT EXISTS {TARGET_CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {TARGET_CATALOG}.{TARGET_SCHEMA}")

base_path = f"{TARGET_CATALOG}.{TARGET_SCHEMA}"

# Helper for fully qualified table names
qt = lambda name: f"{base_path}.{PREFIX}{name}"

# COMMAND ----------
# Utilities

def table_exists(qualified_table: str) -> bool:
    try:
        return spark._jsparkSession.catalog().tableExists(qualified_table)
    except Exception:
        return False

# Utility: cleanup a given table for the current snapshot_date (safe if table doesn't exist)

def cleanup_snapshot(name: str):
    table_name = qt(name)
    if table_exists(table_name):
        spark.sql(f"DELETE FROM {table_name} WHERE snapshot_date = '{SNAPSHOT_DATE}'")

# Utility: write a Spark DF to a Delta table partitioned by snapshot_date (idempotent for that date)

def write_snapshot(df, name: str):
    (
        df.withColumn("snapshot_date", F.lit(SNAPSHOT_DATE))
          .write.mode("append").format("delta")
          .partitionBy("snapshot_date")
          .option("overwriteSchema", True)
          .saveAsTable(qt(name))
    )

# Helper: run SQL but return empty DF if view/table isn't available in this env

def read_or_empty(sql_text: str):
    try:
        return spark.sql(sql_text)
    except Exception:
        return spark.createDataFrame([], schema="_missing STRING")

# COMMAND ----------
# ===== METASTORE-LEVEL INVENTORY VIA INFORMATION_SCHEMA =====
# Prefer system.information_schema (metastore-wide). Some views may not exist in all envs, so we guard reads.

catalogs_df  = read_or_empty("SELECT * FROM system.information_schema.catalogs")
schemata_df  = read_or_empty("SELECT * FROM system.information_schema.schemata")
tables_df    = read_or_empty("SELECT * FROM system.information_schema.tables")
columns_df   = read_or_empty("SELECT * FROM system.information_schema.columns")
views_df     = read_or_empty("SELECT * FROM system.information_schema.views")
functions_df = read_or_empty("SELECT * FROM system.information_schema.routines")

# Privileges (universally useful)
tbl_priv_df  = read_or_empty("SELECT * FROM system.information_schema.table_privileges")
sch_priv_df  = read_or_empty("SELECT * FROM system.information_schema.schema_privileges")

# Optional allowlist filter
if CATALOG_ALLOWLIST:
    allow = tuple(CATALOG_ALLOWLIST)
    schemata_df = schemata_df.where(F.col("catalog_name").isin(*allow))
    tables_df   = tables_df.where(F.col("table_catalog").isin(*allow))
    columns_df  = columns_df.where(F.col("table_catalog").isin(*allow))
    views_df    = views_df.where(F.col("table_catalog").isin(*allow))
    functions_df= functions_df.where(F.col("routine_catalog").isin(*allow))
    tbl_priv_df = tbl_priv_df.where(F.col("table_catalog").isin(*allow))
    sch_priv_df = sch_priv_df.where(F.col("catalog_name").isin(*allow))

# Write snapshots
for name, df in [
    ("catalogs", catalogs_df),
    ("schemata", schemata_df),
    ("tables", tables_df),
    ("columns", columns_df),
    ("views", views_df),
    ("functions", functions_df),
    ("table_privileges", tbl_priv_df),
    ("schema_privileges", sch_priv_df),
]:
    cleanup_snapshot(name)
    write_snapshot(df, name)

# COMMAND ----------
# ===== INVENTORY VIA SDK (not covered well by I_S): External locations, storage creds, volumes, shares, providers, recipients
w = WorkspaceClient()

# External Locations
ext_locs = []
for loc in w.external_locations.list():
    ext_locs.append({
        "name": loc.name,
        "url": loc.url,
        "owner": loc.owner,
        "credential_name": loc.credential_name,
        "read_only": getattr(loc, "read_only", None),
        "created_at": getattr(loc, "created_at", None),
        "created_by": getattr(loc, "created_by", None),
        "updated_at": getattr(loc, "updated_at", None),
        "updated_by": getattr(loc, "updated_by", None),
    })

# Storage Credentials
storage_creds = []
for cred in w.storage_credentials.list():
    storage_creds.append({
        "name": cred.name,
        "owner": cred.owner,
        "read_only": getattr(cred, "read_only", None),
        "comment": getattr(cred, "comment", None),
        "created_at": getattr(cred, "created_at", None),
        "created_by": getattr(cred, "created_by", None),
        "updated_at": getattr(cred, "updated_at", None),
        "updated_by": getattr(cred, "updated_by", None),
    })

# Volumes (per catalog + schema)
vols = []
for cat in w.catalogs.list():
    if CATALOG_ALLOWLIST and cat.name not in CATALOG_ALLOWLIST:
        continue
    for sch in w.schemas.list(cat.name):
        for v in w.volumes.list(cat.name, sch.name):
            vols.append({
                "full_name": v.full_name,
                "catalog_name": cat.name,
                "schema_name": sch.name,
                "volume_type": getattr(v.volume_type, "value", None) if getattr(v, "volume_type", None) else None,
                "storage_location": getattr(v, "storage_location", None),
                "owner": getattr(v, "owner", None),
                "created_at": getattr(v, "created_at", None),
                "created_by": getattr(v, "created_by", None),
                "updated_at": getattr(v, "updated_at", None),
                "updated_by": getattr(v, "updated_by", None),
            })

# Delta Sharing entities
shares, providers, recipients = [], [], []
for s in w.shares.list():
    shares.append({"name": s.name, "owner": s.owner, "created_at": s.created_at, "updated_at": s.updated_at})
for p in w.providers.list():
    providers.append({"name": p.name, "owner": p.owner, "created_at": p.created_at, "updated_at": p.updated_at})
for r in w.recipients.list():
    recipients.append({"name": r.name, "owner": r.owner, "created_at": r.created_at, "updated_at": r.updated_at})

# Convert to Spark & write
sdk_sets = [
    ("external_locations", ext_locs),
    ("storage_credentials", storage_creds),
    ("volumes", vols),
    ("shares", shares),
    ("providers", providers),
    ("recipients", recipients),
]

for name, rows in sdk_sets:
    pdf = pd.DataFrame(rows or [])
    sdf = spark.createDataFrame(pdf) if not pdf.empty else spark.createDataFrame([], schema="name STRING")
    cleanup_snapshot(name)
    write_snapshot(sdf, name)

# COMMAND ----------
# ===== GOLD VIEWS FOR QUICK REPORTING (built from snapshots) =====

spark.sql(f"""
CREATE OR REPLACE VIEW {qt('gold_object_counts')} AS
SELECT snapshot_date, 'catalog' as object_type, COUNT(DISTINCT catalog_name) as n
  FROM {qt('catalogs')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'schema', COUNT(DISTINCT catalog_name || '.' || schema_name)
  FROM {qt('schemata')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'table', COUNT(DISTINCT table_catalog || '.' || table_schema || '.' || table_name)
  FROM {qt('tables')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'view', COUNT(DISTINCT table_catalog || '.' || table_schema || '.' || table_name)
  FROM {qt('views')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'function', COUNT(*) FROM {qt('functions')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'volume', COUNT(*) FROM {qt('volumes')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'external_location', COUNT(*) FROM {qt('external_locations')} GROUP BY snapshot_date
UNION ALL
SELECT snapshot_date, 'storage_credential', COUNT(*) FROM {qt('storage_credentials')} GROUP BY snapshot_date
""")

# Orphan schemata (schema with 0 tables/views/volumes) for the latest snapshot date inserted in this run
spark.sql(f"""
CREATE OR REPLACE VIEW {qt('gold_orphan_schemata')} AS
WITH obj AS (
  SELECT table_catalog as catalog_name, table_schema as schema_name
    FROM {qt('tables')} WHERE snapshot_date = '{SNAPSHOT_DATE}'
  UNION ALL
  SELECT table_catalog, table_schema FROM {qt('views')} WHERE snapshot_date = '{SNAPSHOT_DATE}'
  UNION ALL
  SELECT catalog_name, schema_name FROM {qt('volumes')} WHERE snapshot_date = '{SNAPSHOT_DATE}'
)
SELECT s.catalog_name, s.schema_name, '{SNAPSHOT_DATE}' as snapshot_date
  FROM {qt('schemata')} s
 WHERE s.snapshot_date = '{SNAPSHOT_DATE}'
   AND NOT EXISTS (
       SELECT 1 FROM obj
        WHERE obj.catalog_name = s.catalog_name
          AND obj.schema_name  = s.schema_name
   )
""")

# Top 50 largest schemas by table count
spark.sql(f"""
CREATE OR REPLACE VIEW {qt('gold_top_schemas_by_tables')} AS
SELECT '{SNAPSHOT_DATE}' as snapshot_date,
       table_catalog as catalog_name,
       table_schema  as schema_name,
       COUNT(*) as table_count
  FROM {qt('tables')}
 WHERE snapshot_date = '{SNAPSHOT_DATE}'
 GROUP BY table_catalog, table_schema
 ORDER BY table_count DESC
 LIMIT 50
""")

# COMMAND ----------
# ===== QUICK CHECKS =====

display(spark.table(qt('gold_object_counts')).orderBy(F.col('snapshot_date').desc(), F.col('object_type')))

# COMMAND ----------
# ===== OPTIONAL: SAMPLE QUERIES YOU CAN USE IN A DBSQL DASHBOARD =====

sample_queries = {
  "Object counts": f"SELECT * FROM {qt('gold_object_counts')} WHERE snapshot_date = '{SNAPSHOT_DATE}' ORDER BY object_type",
  "Schemas with no objects": f"SELECT * FROM {qt('gold_orphan_schemata')} ORDER BY catalog_name, schema_name",
  "Top schemas by tables": f"SELECT * FROM {qt('gold_top_schemas_by_tables')} ORDER BY table_count DESC",
  "All tables": f"SELECT table_catalog, table_schema, table_name, table_type, is_insertable_into FROM {qt('tables')} WHERE snapshot_date = '{SNAPSHOT_DATE}' ORDER BY table_catalog, table_schema, table_name",
  "Table privileges": f"SELECT * FROM {qt('table_privileges')} WHERE snapshot_date = '{SNAPSHOT_DATE}' ORDER BY table_catalog, table_schema, table_name, grantee",
  "Schema privileges": f"SELECT * FROM {qt('schema_privileges')} WHERE snapshot_date = '{SNAPSHOT_DATE}' ORDER BY catalog_name, schema_name, grantee",
}

print("
Copy any of these into a DBSQL query:
")
for k, v in sample_queries.items():
    print(f"-- {k}
{v}
")

# DONE ✅
