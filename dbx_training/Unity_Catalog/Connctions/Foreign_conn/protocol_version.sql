/*[DELTA_UNSUPPORTED_DROP_COLUMN] DROP COLUMN is not supported for your Delta table. 
Please enable Column Mapping on your Delta table with mapping mode 'name'.
You can use one of the following commands.
Refer to table versioning at https://docs.microsoft.com/azure/databricks/delta/versioning
*/

--If your table is already on the required protocol version:
ALTER TABLE table_name
SET TBLPROPERTIES ('delta.columnMapping.mode' = 'name')

--If your table is not on the required protocol version and requires a protocol upgrade:
ALTER TABLE table_name SET TBLPROPERTIES (
   'delta.columnMapping.mode' = 'name',
   'delta.minReaderVersion' = '2',
   'delta.minWriterVersion' = '5')