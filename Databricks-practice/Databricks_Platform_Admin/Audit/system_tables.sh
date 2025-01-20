%sh
curl -v -X GET -H "Authorization: Bearer <PAT>" "<db_URL/api/2.0/unity-catalog/metastores/<metastoreID/systemschemas"
curl -v -X PUT -H "Authorization: Bearer <PAT>" "<db_URL/api/2.0/unity-catalog/metastores/<metastoreID/systemschemas/<schema"

schema 
 - Compute
 - Access
 -{"schemas":[{"schema":"storage","state":"AVAILABLE"},
 {"schema":"operational_data","state":"UNAVAILABLE"},
 {"schema":"access","state":"AVAILABLE"},
 {"schema":"billing","state":"ENABLE_COMPLETED"},
 {"schema":"compute","state":"AVAILABLE"},
 {"schema":"marketplace","state":"AVAILABLE"},
 {"schema":"query","state":"AVAILABLE"},
 {"schema":"lakeflow","state":"AVAILABLE"},
 {"schema":"__internal_logging","state":"AVAILABLE"},
 {"schema":"serving","state":"AVAILABLE"},
 {"schema":"mlflow","state":"AVAILABLE"},
 {"schema":"lineage","state":"AVAILABLE"},
 {"schema":"information_schema","state":"ENABLE_COMPLETED"}]}