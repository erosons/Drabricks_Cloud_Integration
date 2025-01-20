"""
     Predictive optimization automatically runs VACUUM on Unity Catalog managed tables. 
     Databricks recommends enabling predictive optimizations for all Unity Catalog managed tables
      to simplify data maintenance and reduce storage cost

    # SETTING UP PREDICTIVE OPTIMIZATION

        Access the accounts console.

        Navigate to Settings, then Feature enablement.

        Select Enabled next to Predictive optimization.
        
A shorter retention duration means less historical data is kept, which could be beneficial for storage optimization but limits the ability to perform historical audits or rollbacks.
"""    


"""
VACUUM might leave behind empty directories after removing all files from within them.
 Subsequent VACUUM operations delete these empty directories.
"""

SET this global parameter retention period check 

>>> ALTER TABLE table_name SET TBLPROPERTIES ('delta.deletedFileRetentionDuration' = '30 days');
spark.conf.set('spark.databricks.delta.retentionDurationCheck.enabled') returns True

# But when you need to do immediate clean up  but not advised.
spark.conf.set('spark.databricks.delta.retentionDurationCheck.enabled','false')

>>> ALTER CATALOG [catalog_name] {ENABLE | DISABLE} PREDICTIVE OPTIMIZATION;
>>> ALTER {SCHEMA | DATABASE} schema_name {ENABLE | DISABLE} PREDICTIVE OPTIMIZATION;



# Predictive optimization is not available in all regions. See Databricks clouds and regions.
# Predictive optimization does not run OPTIMIZE commands on tables that use Z-order.
# Predictive optimization does not run VACUUM operations on tables with a file retention window configured below the default of 7 days.
#  See Configure data retention for time travel queries.
# Predictive optimization does not perform maintenance operations on the following tables:

#     Tables loaded to a workspace as Delta Sharing recipients.

#     External tables.

#     Materialized views. See Use materialized views in Databricks SQL.

#     Streaming tables. See Load data using streaming tables in Databricks SQL.
