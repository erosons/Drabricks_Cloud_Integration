-- CREATE a CTAS TABLE inferring from external location
-- work well with Well defined SCHEMA such as Parquet
-- CSV FIle Will show a signiCant Limitation


CREATE OR REPLACE TABLE sales AS
SELECT * FROM parquet.`${DA.paths.datasets}/ecommerce/raw/sales-historical`;


-- When dealing with CSV 
USE CATALOG main;

CREATE TABLE IF NOT EXISTS IngestionData_bronze
USING CSV
OPTIONS (
  header = "true",
  mode = "FAILFAST", --abort parsing if a malformed record is encountered with a RuntimeException
  delimiter = ","
)
LOCATION "abfss://{}/csv_loader";


-- CREATING TABLE WITH with auto generated columns , when the columns are not specified
-- CTAS DOES NOT SUPPORT SCHEMA DECLARATION
CREATE OR REPLACE TABLE purchase_dates (
  id STRING, 
  transaction_timestamp STRING, 
  price STRING,
  date DATE GENERATED ALWAYS AS (
    cast(cast(transaction_timestamp/1e6 AS TIMESTAMP) AS DATE))
    COMMENT "generated based on `transactions_timestamp` column")

------------------------------------
-- COULUMN AUTO GENERATION
-------------------------------------
%sql
CREATE OR REPLACE TABLE purchase_dates (
  orderID STRING, 
  orderdate STRING,
  Shipdate DATE GENERATED ALWAYS AS (  auto genrateion
    try_cast(to_date(orderdate, 'M/d/yyyy') AS DATE))
    COMMENT "generated based on `transactions_timestamp` column"
);

-- APPEND DATA TO THE TABLE
INSERT INTO purchase_dates
SELECT orderID, orderdate, try_cast(to_date(orderdate, 'M/d/yyyy') AS DATE) AS Shipdate 
FROM ingestiondata_bronze;


%sql
DROP TABLE IF EXISTS purchase_dates; 

CREATE OR REPLACE TABLE purchase_dates (
  orderID STRING, 
  orderdate STRING,
  Shipdate DATE COMMENT "generated based on `transactions_timestamp` column"
);

INSERT INTO purchase_dates
SELECT 
  orderID, 
  orderdate, 
  CAST(current_date() AS DATE) AS Shipdate 
FROM ingestiondata_bronze;