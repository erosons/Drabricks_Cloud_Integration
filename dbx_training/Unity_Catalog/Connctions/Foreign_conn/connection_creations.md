# Step 1: Create a Connection
    Before creating a foreign catalog, you must first establish a connection
    to the external data source. This could be a connection to cloud storage (like AWS S3, Azure Data Lake Storage, or Google Cloud Storage) or a database (like PostgreSQL, MySQL, etc.).
    Here's a general example of creating a connection to an S3 bucket:


        CREATE CONNECTION my_s3_connection
        TYPE 'S3'
        URL 's3://my-bucket-name'
        OPTIONS (
            'AWS_ACCESS_KEY_ID' = '<your_access_key_id>',
            'AWS_SECRET_ACCESS_KEY' = '<your_secret_access_key>'
        )

# Step 2: Create a Foreign Catalog
        Once the connection is established, you can create a foreign catalog
        that references this connection. The foreign catalog acts as a virtual database 
        catalog within Unity Catalog, allowing you to access and manage the data from the external source.
        This command creates a foreign catalog named my_foreign_catalog that maps to the data accessible via the my_s3_connection


        CREATE FOREIGN CATALOG my_foreign_catalog
        AT CONNECTION my_s3_connection


# Step 3: Create TBL WITH EXTERNAL DATA AND MANAGED METADATA
        After creating the foreign catalog, you can define tables within this catalog
        that reference specific datasets in the external source. For example, if you have data
        n Parquet format stored in S3, you can create a table that references this data.

        CREATE TABLE my_catalog_database.my_external_table
        USING PARQUET
        OPTIONS (
            catalog = 'my_foreign_catalog',
            path = 's3://my-bucket-name/data-folder/my-data-file.parquet'
        )

# Step 4: Querying the Table
Once the table is set up, you can query it just like any other table in Databricks:


SELECT * FROM my_catalog_database.my_external_table LIMIT 10;
