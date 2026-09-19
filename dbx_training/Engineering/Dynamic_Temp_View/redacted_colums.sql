CREATE OR REPLACE VIEW dynamic_view
AS 
SELECT 
  CASE WHEN is_account_group_member('grp_name') THEN column ELSE 'REDACTED' END as column
FROM TABLE
