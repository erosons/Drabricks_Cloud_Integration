## Introduction to Delta Lake using Data Frames 

Delta Lake tables provide ACID compliant updates to tables backed by data files in cloud object storage.


As part of this section or module we will deep dive into Delta Lake using Data Frames. Even though Big Data is here for quite some time, performing ACID Transactions or CRUD operations is not matured enough until recent times.

When we build data lakes using Big Data eco system, it is imperative to work with tables on which we have to perform ACID Transactions or CRUD Operations
Here are the common operations that are known as 
    ACID Transactions or CRUD Operations
      - **INSERT*
      - **UPDATE
      - **DELETE*
      - **UPSERT OR MERGE*
      
 Databricks or delta.io have introduced Delta Lake primarily to simplify the process of performing CRUD Operations leveraging powerful Spark Engine,
 
 Here are the topics that are covered as part of this section or module using Spark Data Frames.
 
    - Overview of creating Data Frames using JSON String
    - Writing data in Data Frame into files using Delta Format
    - Using delta.tables.DeltaTable to perform common operations on top of files created using  ** Delta Format**
    - Updating data in files that are created using Delta Format, We can now 
    - Deleting data from files that are created using Delta Format 
    - Merge or Upsert data in files that are created using Delta Format 
    - Recovery of data in Delta format files either by point in time or version  
    - Managing Delta Format Files using vacuum -> Cleanup Operations of deployments files
    - Compacting too many small files into fewer large files created using Delta Format. 
You will also understand some of the internals as you go through the topics under this section or module.","commandVersion"