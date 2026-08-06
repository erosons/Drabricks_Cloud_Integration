CREATE CATALOG IF NOT EXISTS democatalog

CREATE CATALOG IF NOT EXISTS democatalog
LOCATION 'abfss://uceastus001@dbdlsuseat001.dfs.core.windows.net/external_query1' AS
SELECT
  m.*
FROM
  system.information_schema.metastores m
  JOIN system.information_schema.metastore_privileges p ON m.metastore_id = p.metastore_id


-- REVIEW CATALOG
SHOWS CATALOGS;

DESCRIBE CATALOG EXTENDED demoCatalog

--- REVIE SCHEMA
DESCRIBE SCHEMA EXTENDED democatalog.demo_schema

--CREATE SCHEMA WITH EXTERNAL LOCATION
USE CATALOG demoCatalog
CREATE DATABASE|SCHEMA IF NOT EXISTS SCHEMA-NAME
MANAGED LOCATION --<--locathpath->
--COMMENTS <--->
WITH DBPROPERTIES (property-key = property_value)

USE CATALOG democatalog;
CREATE SCHEMA IF NOT EXISTS demo_schema

USE CATALOG democatalog;
CREATE DATABASE IF NOT EXISTS demo_schema2