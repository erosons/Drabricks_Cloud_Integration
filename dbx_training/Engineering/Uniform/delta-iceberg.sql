-- Runtime 16.4, or later
CREATE TABLE my_table (
  id INT,
  name STRING,
  region STRING
)
USING DELTA
TBLPROPERTIES (
  'delta.ColumnMapping.mode' = 'name',
  'delta.universalFormat.enabled' = 'true',
  'delta.enableIcebergCompactV2' = 'true'
);
