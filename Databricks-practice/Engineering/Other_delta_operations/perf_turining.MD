<!-- Samples Data for Performance  -->
# Version, Optimize, Vacuum in Delta Lake

# Note that while some of the keywords used here aren't part of standard ANSI SQL, all Delta Lake operations can be run on Databricks using SQL
# Learning Objectives

# By the end of this lesson, you should be able to:

#     Use OPTIMIZE to compact small files
#     Use ZORDER to index tables
#     Describe the directory structure of Delta Lake files
#     Review a history of table transactions
#     Query and roll back to previous table version
#     Clean up stale data files with VACUUM

SQL.RUN
DESCRIBE EXTENDED students -> Allows us to see important metadata about our table.
Describe DETAIL -> Allows us to futher explore table meta data , helps to know the number of files currently been used by the delta Tables.

# However , in the delta path we could be seeing alot paruet files. but the delta log helps know weather files are still valid.
Query the lastest .json file in _delta.log to know what is parquet files are valid.


%python
display(spark.sql(f"SELECT * FROM json.`{DA.paths.user_db}/students/_delta_log/00000000000000000007.json`"))

The add column contains a list of all the new files written to our table; the remove column indicates those files that no longer should be included in our table.

#### When we query a Delta Lake table, the query engine uses the transaction logs to resolve all the files that are valid in the current version, and ignores all other data files.




CREATE TABLE students
  (id INT, name STRING, value DOUBLE);
  
INSERT INTO students VALUES (1, "Yve", 1.0);
INSERT INTO students VALUES (2, "Omar", 2.5);
INSERT INTO students VALUES (3, "Elia", 3.3);

INSERT INTO students
VALUES 
  (4, "Ted", 4.7),
  (5, "Tiffany", 5.5),
  (6, "Vini", 6.3);
  
UPDATE students 
SET value = value + 1
WHERE name LIKE "T%";

DELETE FROM students 
WHERE value > 6;

CREATE OR REPLACE TEMP VIEW updates(id, name, value, type) AS VALUES
  (2, "Omar", 15.2, "update"),
  (3, "", null, "delete"),
  (7, "Blue", 7.7, "insert"),
  (11, "Diya", 8.8, "update");
  
MERGE INTO students b
USING updates u
ON b.id=u.id
WHEN MATCHED AND u.type = "update"
  THEN UPDATE SET *
WHEN MATCHED AND u.type = "delete"
  THEN DELETE
WHEN NOT MATCHED AND u.type = "insert"
  THEN INSERT *;

SQL.RUN
DESCRIBE HISTORY students   => Version Histories

### Compacting Small Files and Indexing

Small files can occur for a variety of reasons; in our case, we performed a number of operations where only one or several records were inserted.

Files will be combined toward an optimal size (scaled based on the size of the table) by using the OPTIMIZE command.

# OPTIMIZE 
will replace existing data files by combining records and rewriting the results.

When executing OPTIMIZE, users can optionally specify one or several fields for **ZORDER indexing **. While the specific math of Z-order is unimportant, it speeds up data retrieval when filtering on provided fields by colocating data with similar values within data files.

SQL.RUN
OPTIMIZE students
ZORDER BY id

<!-- Cleaning Up Stale Files -->

Databricks will automatically clean up stale log files (> 30 days by default) in Delta Lake tables. Each time a checkpoint is written, Databricks automatically cleans up log entries older than this retention interval.

While Delta Lake versioning and time travel are great for querying recent versions and rolling back queries, keeping the data files for all versions of large production tables around indefinitely is very expensive (and can lead to compliance issues if PII is present).

If you wish to manually purge old data files, this can be performed with the VACUUM operation.

Uncomment the following cell and execute it with a retention of 0 HOURS to keep only the current version:

## SET spark.databricks.delta.retentionDurationCheck.enabled = false;
## SET spark.databricks.delta.vacuum.logging.enabled = true;

VACUUM students RETAIN 0 HOURS DRY RUN  -> You can perform a dry before performing the acrual operations