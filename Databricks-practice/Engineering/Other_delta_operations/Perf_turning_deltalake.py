from delta.tables import *
from delta_reader import spark

# See contents of the Delta table path 
%fs ls LocalPath/ExternalStorageLocation

deltaTable = DeltaTable.forName(spark, "Tablename") -> in the unity catalog
deltaTable = DeltaTable.forPath(spark, "deltaPath") -> in external storage location

# For peformance turning 
# Will help aggregated smaller files into gaint file , but at the xpense of Time travel and versioning
# Cleanup old clean up old snapshots. You can do this by running the vacuum operation:

deltaTable.optimize().executeCompaction()  
deltaTable.vacuum(0)  # https://docs.databricks.com/en/sql/language-manual/delta-vacuum.html