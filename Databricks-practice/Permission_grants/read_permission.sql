GRANT <privilege-type> ON <securable-type> <securable-name> TO <principal>
GRANT CREATE TABLE ON SCHEMA main.default TO `finance-team|username`;
GRANT USE SCHEMA ON SCHEMA main.default TO `finance-team`;
GRANT USE CATALOG ON CATALOG main TO `finance-team`;
GRANT SELECT ON CATALOG main TO `finance-team`;
GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG city_bike TO `groupname|username;