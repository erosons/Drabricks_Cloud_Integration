DROP TABLE IF EXISTS myTableName;
CREATE TABLE IF NOT EXISTS <myTableName>
USING JDBC
OPTIONS (
    url = "jdbc:{databaseServerType}://{jdbcHostname}:{jdbcPort}",
    dbtable = "{jdbcDatabase}.table",
    user = "{jdbcUsername}",
    password = "{jdbcPassword}"
) 


DESCRIBE EXTENDED myTableName;