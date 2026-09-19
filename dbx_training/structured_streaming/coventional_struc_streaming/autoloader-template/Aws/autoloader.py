schema_loc        = "s3://redshift-stagingarea/meta/schemas/superstore"
checkpoint_read   = "s3://redshift-stagingarea/meta/checkpoints/superstore_read"
checkpoint_write  = "s3://redshift-stagingarea/meta/checkpoints/samplesupertore"
src_path          = "s3://redshift-stagingarea/raw/superstore"   # <— changed!
tablename:str = "main.default.samplesupertore"

streamdf = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','csv') \
                .option('cloudFiles.useNotifications','true') \
                .option("path",src_path) \
                .option("databricks.serviceCredential","autoloaderiam") \
                .option("cloudFiles.schemaLocation", schema_loc) \
                .option("checkpointLocation", checkpoint_read) \
                .option("maxFilesPerTrigger", 1) \
                .load()

# writing files to path object storage
streamdf.writeStream \
  .format("delta") \
  .option("path", src_target) \
  .partitionBy("State", "Segment") \
  .option("checkpointLocation", checkpoint) \
  .trigger(once=True) \
  .toTable(tablename)