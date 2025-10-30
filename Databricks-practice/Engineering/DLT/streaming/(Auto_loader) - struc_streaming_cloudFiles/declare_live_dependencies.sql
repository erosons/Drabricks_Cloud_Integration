There are two types of DLT TABLESPACE 
  -  LIVE : Materialized views
  -  STREAMING TABLE: Easily ingest files from storage as they are uploaded  (list_dir or Notifications)
                      - Cofigurable for schema inference and schema evolution
                      -  Aviod duplication and wasted work

Data Ingestion: The primary difference between a live table and a streaming live table is how data is read—using spark.read for batch data and spark.readStream for streaming data in python @dlt


ExamplE of STREAMING LIVE TABLE
CREATE STREAMING LIVE TABLE  table_name
USING cloudFiles(/data, "json")

SQL STREAM() Function -> can stream an Delta table as a stream as a new record arrives.
The streamming tables must only be append NO DML (DELETE,UPDATE,UPSERT) are NOT allowed.

SQL:"""

CREATE OR REFRESh STREAMING LIVE TABLE mystream
 AS SELECT *
    FROM STREAM(my_delta_table)
"""


CREATE LIVE TABLE IF NOT EXISTS live_table
AS SELECT * FROM table_name

Downstream:

CREATE LIVE TABLE IF NOT EXISTS report_table
AS SELECT * FROM LIVE.live_table

live_table  => report_table

"""
Dependencies owned by other producers are just read from the catalog or spaf data SOURCE

LIVE dependencies from the same pipeline are read from the LIVE schema.

DLT detects LIVE dependencies and executes all operations in the correct order.

DLT handles parrallelism and retries for you. and captures the lineage of the data.
"""


# COMMAND ----------

SQL = """

CONSTRAINT valid_timestamps
  EXPECT(timestamp > '2021-01-01') 

ON VIOLATION DROP

"""

# COMMAND ----------
Python = """
@dlt.expect_or_drop(
    "valid_timestamps",
    timestamp > '2021-01-01'
)

"""

dlt OFFERS Flexible POLICIES to enforce data quality,consistency and how handle records that violate expectations.
- Track : Number of bad records
- Drop bad records
- Abort processing for a single bad records

