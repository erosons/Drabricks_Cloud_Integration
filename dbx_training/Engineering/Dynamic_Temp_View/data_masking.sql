CREATE OR REPLACE VIEW dynamic_view
AS 
   SELECT 
CASE WHEN is_account_group_member('grp_name') THEN column ELSE dynamic_making(column) END as column
   FROM TABLE
WHERE 
  CASE WHEN is_account_group_member('grp_name') THEN TRUE
ELSE device_number < 30