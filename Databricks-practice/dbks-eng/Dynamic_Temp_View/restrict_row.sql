CREATE OR REPLACE VIEW dynamic_view
AS 
  SELECT 
*
  FROM TABLE
WHERE 
  CASE WHEN is_account_group_member('grp_name') THEN TRUE
ELSE device_number < 30