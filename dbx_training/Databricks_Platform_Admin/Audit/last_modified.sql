%sql
SELECT
  table_name,
  last_altered,
  table_owner,
  created_by,
  last_altered,
  last_altered_by,
  table_catalog
FROM
  information_schema.tables
WHERE
  date_diff(CURRENT_DATE(), last_altered) < 1