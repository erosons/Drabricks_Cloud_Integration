import sys
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions

# Retrieve Glue job arguments
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'S3_INPUT_PATH', 'ICEBERG_CATALOG', 'ICEBERG_DATABASE', 'ICEBERG_TABLE'])

conf_list = [
    #Configs needed for Iceberg
    #file:/home/glue_user/workspace/spark-warehouse

    ("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"),
    ("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog"),
    ("spark.sql.catalog.glue_catalog.warehouse", "s3://lakehouse/stageZone_iceberg/ghactivity-data/"),
    ("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog"),
    ("spark.sql.catalog.glue_catalog.io-impl","org.apache.iceberg.aws.s3.S3FileIO")
    ]

# Initialize Spark, GlueContext, and Job
spark_conf = SparkConf().setAll(conf_list)
spark = SparkSession.builder.config(conf=spark_conf).getOrCreate()
sc = spark.SparkContext()
glueContext = GlueContext(sc)
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Define input data path and Iceberg table details
s3_input_path = args['S3_INPUT_PATH']
iceberg_catalog = args['ICEBERG_CATALOG']  # AWS Glue catalog name for Iceberg
iceberg_database = args['ICEBERG_DATABASE']
iceberg_table = args['ICEBERG_TABLE']

# Read data from S3
df = spark.read.format("parquet").load(s3_input_path)
df.createTempView('tem_table')

# # Write data to Iceberg table in Glue Data Catalog
# iceberg_table_path = f"glue_catalog.{iceberg_database}.{iceberg_table}"

# df.write.format("iceberg") \
#     .mode("overwrite") \
#     .option("path", f"s3://{iceberg_database}/{iceberg_table}/") \
#     .saveAsTable(iceberg_table_path)

# Create new table and insert data from temp_table
#iceberg_table_path = f"glue_catalog.{iceberg_database}.{iceberg_table}"
if not spark.catalog.tableExists('glue_catalog.dremio.SMT_customer15'):
    sql = f'''
        create table if not exists glue_catalog.dremio.SMT_customer15
        using iceberg 
        tblproperties ('table_type'='ICEBERG','format-version'='2', 
        'write.delete.mode'='copy-on-write',
        'write.update.mode'='merge-on-read',
        'write.merge.mode'='merge-on-read',
        'write.object-storage.enabled'=true)
        location "s3://dev-/stageZone_iceberg/iceber_repo/smt-data/"
        AS 
        SELECT * FROM temp_table'''
    spark.sql(sql)    
else:   
#upsert
    sql = f''' 
        merge into  glue_catalog.dremio.SMT_customer15 target
        using (select * from from temp_table) source
        on target."Account_No" = source."Account_No"
        and target."ID" = source."ID"
        and target.UsageDate=source.UsageDate
        and target.filetrackid=source.filtrackid
        when matched then
        update set *
        when not matched then 
        insert * 
        ''' 
    spark.sql(sql)

# Commit the job
job.commit()
 
