-- DEEP CLONE fully copies data and metadata from a source table to a target. This copy occurs incrementally, so executing this command again can sync changes from the source to the target location.

CREATE OR REPLACE TABLE purchases_clone
DEEP CLONE purchases;

-- SHALLOW CLONE copies only the metadata of a source table to a target. This is useful when you want to create a new table with the same schema as an existing table, but without copying the data.

CREATE OR REPLACE TABLE purchases_clone
SHALLOW CLONE purchases;