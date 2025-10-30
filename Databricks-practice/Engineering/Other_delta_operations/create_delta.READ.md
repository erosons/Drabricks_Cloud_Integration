**CREATE OR REPLACE TABLE (CRAS)-> COMPLETE SCHEMA OVERWRITE** 

We can use overwrites to atomically replace all of the data in a table. There are multiple benefits to overwriting tables instead of deleting and recreating tables:

    Overwriting a table is much faster because it doesn’t need to list the directory recursively or delete any files.
    The old version of the table still exists; can easily retrieve the old data using Time Travel.
    It’s an atomic operation. Concurrent queries can still read the table while you are deleting the table.
    Due to ACID transaction guarantees, if overwriting the table fails, the table will be in its previous state.

Spark SQL provides two easy methods to accomplish complete overwrites.

Some students may have noticed previous lesson on CTAS statements actually used CRAS statements (to avoid potential errors if a cell was run multiple times).

**CREATE OR REPLACE TABLE (CRAS)** statements fully replace the contents of a table each time they execute.

SQL :
CREATE OR REPLACE TABLE events AS
SELECT * FROM parquet.`${da.paths.datasets}/ecommerce/raw/events-historical`

# Create or replace the Delta table
df.write.format("delta").mode("overwrite").option("**overwriteSchema", "true"**).saveAsTable("main.default.sample_table")


# ###################
**INSERT OVERWRITE** 
# ###################

provides a nearly identical outcome as above: data in the target table will be replaced by data from the query.

INSERT OVERWRITE:

    Can only overwrite an existing table, not create a new one like our CRAS statement
    Can overwrite only with new records that match the current table schema -- and thus can be a "safer" technique for overwriting an existing table without disrupting downstream consumers
    Can overwrite individual partitions

SQL :
INSERT OVERWRITE sales
SELECT * FROM parquet.`${da.paths.datasets}/ecommerce/raw/sales-historical/`

new_df.write.format("delta").mode(**"overwrite"**).saveAsTable("main.default.sample_table")


# ###################
**INSERT INTO ** 
# ###################
We can use INSERT INTO to atomically append new rows to an existing Delta table. This allows for incremental updates to existing tables, which is much more efficient than overwriting each time.

Append new sale records to the sales table using INSERT INTO.

SQL :
INSERT INTO sales
SELECT * FROM parquet.`${da.paths.datasets}/ecommerce/raw/sales-30m`

# ###################
**INSERT INTO ** 
# ###################
provides SQL engineers an idempotent option to incrementally ingest data from external systems.
Note that this operation does have some expectations:
    Data schema should be consistent
    Duplicate records should try to be excluded or handled downstream