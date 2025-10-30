# https://docs.databricks.com/en/ingestion/cloud-object-storage/auto-loader/index.html
# How does Auto Loader track ingestion progress?

As files are discovered, their metadata is persisted in a scalable key-value store (RocksDB) in the checkpoint location of your Auto Loader pipeline. This key-value store ensures that data is processed exactly once.

In case of failures, Auto Loader can resume from where it left off by information stored in the checkpoint location and continue to provide exactly-once guarantees when writing data into Delta Lake. 

# TYPES OF AUTO LOADER
 Directory List: 
    - Identify new files by listing the input directory.Directory listing modes allows you to quickly start Auto Loader without permission configurations other than access to your data on AWS s3, suitable for scenario where only fe files need to be streamed in on regular basis. default in 7.2 runtime an dabove

 File Notification :
    USes AWS SNS and SQS service that subcribe to file events from input directory. Automatically sets up AWS SQS and SNS . FIle notification is mode is more performant and scalale for large directories. IAM permissions are required for the two services and specify as .option("ClouFIles,useNotification", "true")
   