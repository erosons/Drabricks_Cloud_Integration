--TYPES OF TABLES 
/*
 ## MANAGED TABLES (Good for Analyst)
===================
- Databaricks the underlying data and the metadata
- EVERY TABLE|SCHEMA CREATION if  an external location is not specified default to managed TABLE|SCHEMA
- ALL managed Tables are Delta files format which privde the ACID compliance
- Dropping a Table drops the underlying data and metadata


EXTERNAL TABLES|UNMANAGED (Good for Data Engineers, because of its Flexibility)
=========================
- Databricks managed the  metadata only and not the data
- When creating a location has to be specified
- Dropping and external table data is unaffected
- File Format-> delta,ORC,parquet,avro,csv,json

*/
COMMONS ERRORS:
- Error while reading file abfss:REDACTED_LOCAL_PART@dbsstg001extloc.dfs.core.windows.net/citybike/JC-202207-citbike-tripdata.csv. java.io.IOException

SOLUTION :
CHECK FILE FORMAT and use corect reader and Refresh Metadata

COMMONS ERRORS:
ErrorClass=INVALID_PARAMETER_VALUE.LOCATION_OVERLAP] Input path url 'abfss://extlocation@dbsstg001extloc.dfs.core.windows.net/citybike' overlaps with other external tables or volumes within 'CreateTable' call. Conflicting tables/volumes: course_project.citybike_ext.city_bike.

SOLUTION : 
Writing to an existing table location in the schema


--REFRESHING TABLE META DATA
REFRESH TABLE course_project.citybike_ext.city_bike;

-- Managed tabled ------
use catalog democatalog;
use schema demo_schema;
Create table test1 (
  column_1 INT,
  column_2 STRING
);


--EXTERNAL TABLE CREATION---
CREATE SCHEMA city_bke

CREATE TABLE --tablename
Table  SCHEMA SPECIFICATION
USING FILE FORMAT (optional)
LOCATIONS PATH
OPTIONS CLAUSE (optional)

Example ->

CREATE EXTERNAL TABLE city_bike_ext
( ride_id	string,
  rideable_type	string,
  started_at	timestamp,
  ended_at	timestamp,
  start_station_name	string,
  start_station_id	string,
  end_station_name	string,
  end_station_id	string,
  start_lat	double,
  start_lng	double,
  end_lat	double,
  end_lng	double,
  member_casual	string)
USING PARQUET
LOCATION 'abfss://extlocation@dbsstg001extloc.dfs.core.windows.net/citybike/'

CREATE EXTERNAL TABLE course_project.citybike_ext.city_bike
USING CSV
OPTIONS (
  path 'abfss://extlocation@dbsstg001extloc.dfs.core.windows.net/citybike/',
  header 'true',
  inferSchema 'true'
);

CREATE TABLE city_bike
USING CSV|Parquet
LOCATION 'abfss://extlocation@dbsstg001extloc.dfs.core.windows.net/citybike/'

CREATE EXTERNAL TABLE city_bike
( ride_id	string,
  rideable_type	string,
  started_at	timestamp,
  ended_at	timestamp,
  start_station_name	string,
  start_station_id	string,
  end_station_name	string,
  end_station_id	string,
  start_lat	double,
  start_lng	double,
  end_lat	double,
  end_lng	double,
  member_casual	string)
USING CSV
OPTIONS (
  path 'abfss://extlocation@dbsstg001extloc.dfs.core.windows.net/citybike/',
  header 'true'
);




































