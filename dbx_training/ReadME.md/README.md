# Databricks Accessible Files Systems
>>> %fs ls /FileStore`
>>> display(dbutils.fs.ls('dbfs:/Workspace/Users/S.Eromonsei@shell.com/retail_db'))

path	name	size
dbfs:/FileStore/	FileStore/	0
dbfs:/Volume/	Volume/	0
dbfs:/Volumes/	Volumes/	0
dbfs:/databricks-datasets/	databricks-datasets/	0
dbfs:/databricks-results/	databricks-results/	0
dbfs:/tmp/	tmp/	0
dbfs:/volume/	volume/	0
dbfs:/volumes/	volumes/	0

# ###################
## Db.utils use cases
# ###################

for i in dbutils.fs.ls("/FileStore/tables/demo"):
    if i.name.endswith(".csv"):
        df = spark.read.format("csv").option("header", "true").load("dbfs:/FileStore/tables/demo/SampleSuperstore_in_.csv")
        tempSQL=df.createOrReplaceTempView("SampleSuperstore")
        spark.sql(f"select sum(profit) as totalProfit from SampleSuperstore group by shipDate ").show()
    else:
        exit()

df = spark.read.json([i.path for i in dbutils.fs.ls("s3://acm-test-bucket/sandbox/")][0])
df.show(5)

outcome:

path	                                                   name	          size	  modificationTime
s3://acm-test-bucket/sandbox/2024-09-30-10.json.gz	2024-09-30-10.json.gz	110148970	1727756440000
s3://acm-test-bucket/sandbox/2024-09-30-11.json.gz	2024-09-30-11.json.gz	105285085	1727756443000
s3://acm-test-bucket/sandbox/2024-09-30-12.json.gz	2024-09-30-12.json.gz	113039317	1727756445000
s3://acm-test-bucket/sandbox/2024-09-30-13.json.gz	2024-09-30-13.json.gz	121623904	1727756448000
s3://acm-test-bucket/sandbox/2024-09-30-14.json.gz	2024-09-30-14.json.gz	123208950	1727756450000
s3://acm-test-bucket/sandbox/2024-09-30-15.json.gz	2024-09-30-15.json.gz	122981936	1727756453000


# Workspace:
    This is the collaborative environment where users can organize their work in folders, create and share notebooks, libraries, and experiments. It acts as the central hub for all project-related activities, providing tools for version control and access management.

# Catalog:
    The Databricks Catalog is a metadata management service that allows users to organize, discover, and manage data assets within their Databricks workspace. It supports structuring data in databases and tables, and offers a searchable repository of registered data objects.

# Workflow:
    Databricks supports complex data workflows, enabling scheduling and automation of notebooks and scripts as jobs. Workflows can be triggered on a schedule or in response to events, and can be monitored through the UI.

# Compute:
    Users can configure and manage Spark clusters that scale automatically based on workload. These clusters can be customized with various machine types and configurations to optimize for different computational needs.

# SQL Editor:
    The SQL Editor in Databricks allows users to write, execute, and test SQL queries directly within the UI. This feature supports autocompletion, syntax highlighting, and direct integration with the catalog for easy access to data assets.

# Dashboards:
    Users can create interactive dashboards directly from SQL queries or notebooks. These dashboards can be shared with other users and stakeholders, providing visual insights into the analyzed data.

# Alerts:
    Databricks enables setting up alerts based on specified criteria in data streams or job performances. Alerts can notify users via email or other integrations when certain conditions are met, facilitating proactive management of data processes.

# Query History:
    This feature records all SQL queries executed in the workspace, allowing users to review past queries, monitor usage, and optimize performance over time.

# SQL Warehouse:
    Previously known as Databricks SQL, this feature is optimized for running SQL queries at scale on data lakes. It provides low-cost access to data with high concurrency and performance optimizations, suitable for BI and reporting use cases.
# Job Runs:
    Databricks tracks each execution of a scheduled job or notebook. Users can review detailed logs, metrics, and outcomes of these job runs, aiding in debugging and performance tuning.
# Data Ingestion:
    The platform supports various methods for data ingestion, from batch processing to real-time streaming. Integration with common data sources and services facilitates seamless data import into the system.

# Delta Live Tables:
    A feature designed for building reliable data pipelines using simple SQL and Python code. Delta Live Tables automate data pipeline workflows, ensuring data quality with declarative data engineering and automated error handling.

 
# ########################################
### databricks CLI for local development
# ########################################
>> pip install databricks-cli


  ## For Authentication
    * Go to Databricks UI
    * Go to User Settings and generate token
    * Configure Databricks CLI using profile. Paste Databricks URL and token when prompted.

    Get the token from databrick Environment
    
    databricks configure --profile <Profile|Default>
   
   >> databricks configure --token 
     prompts for URL :
     prompts token : 

  ## Configure Databricks CLI (Command line utility
   cluster-policies  Utility to interact with Databricks cluster policies.
    clusters          Utility to interact with Databricks clusters.
    configure         Configures host and authentication info for the CLI.
    fs                Utility to interact with DBFS.
    groups            Utility to interact with Databricks groups.
    instance-pools    Utility to interact with Databricks instance pools.
    jobs              Utility to interact with jobs.
    libraries         Utility to interact with libraries.
    pipelines         Utility to interact with Databricks Delta Live Tables
                        Pipelines.
    repos             Utility to interact with Repos.
    runs              Utility to interact with the jobs runs.
    secrets           Utility to interact with Databricks secret API.
    stack             [Beta] Utility to deploy and download Databricks resource
                        stacks.
    tokens            Utility to interact with Databricks tokens.
    unity-catalog     Utility to interact with Databricks Unity Catalog.
    workspace         Utility to interact with the Databricks workspace.
  )
  
    * Validate by running below command.
   >> databricks fs ls --profile demo


#### Install databricks Connect Client base on your cluster runttime
   https://docs.databricks.com/en/dev-tools/databricks-connect/python/index.html
   Virtual Environment setup  -> 
     https://www.databricks.com/blog/2022/07/07/introducing-spark-connect-the-power-of-apache-spark-everywhere.html

  >> conda create --name <virtualenv> python=version

    Setup you databrickCLI for OAuth authentication
    Make sure there is no spark runtime deployed to aviod any form of conflict with databrick spark runtime

  Double check if pyspark is installed 
  >>> pip uninstall pysaprk
  >>  pip install -U databricks-connect==(latest runtime LTS)
  >>> pip install --upgrade databricks-connect==15.1.*

On CLI 
    >>> databricks configure
    Configure connection properties through parameterization from your secrity vault
    databricks workspaceURL -> ?
    PAT -> ?
    cluster ID -> ?

# ################
## NOTEBOOK CLI
# ################
%python
%pip install databricks-cli

# Use the Databricks CLI to create a secret scope backed by Azure Key Vault
!databricks secrets create-scope --scope <scope-name> \
  --scope-backend-type AZURE_KEYVAULT \
  --resource-id <azure-key-vault-resource-id> \
  --dns-name <azure-key-vault-dns-name>



## Storage Mount:(azure, AWS)

    Azure storage Mount -> This will be achieved using to integrate SPN via active directory which makes the container available across all the cluster.-> image
    This storage access can be restricted to the level of workspaces on isolating  and accessible by cluster within that workspace only
        1. The Azure directory -> Go to App registration and register an App 9for Signle Tenant
        2. Create Certificate and Secret
            - get tenantID
            - get applicationID
            - get the secrets
   >> databricks secrets create-scope --scope <scope-name>  --initial-manage-principal users  (optional) --profile demo (optional)
   >> databricks secrets list-scopes (to list scopes)
    Types of scores
       Scope  Backend Type using keyVault
       demo   DATABRICKS
   >>> databricks secrets put --scope dataengng-scope --key azuremount --string-value <token> --profile(optional)
   RETURN the Azure portal
     - On the storage  acoount IAM  and role assignment
    -  Map the APP SPN that was created with storage account (data storage container contributor)

NOTE make sure soft delete is not enable , in the data management,-> data protection

>>> run the configuration setup

 Validate by
   >> dbutils.fs.ls("/mnt/mymountadls")

## AWS S3 integration with Databricks
  Create Iam Role with sts(trust relationship attached) and attached the policies to the IAM
    - s3 polices
    - glue polices
Modify the databrick deployment IAM role and add the IAM:PassRole for the role to be assumed
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::<aws-account-id-databricks>:role/<iam-role-for-s3-access>"
    }

COPY the instance ARN role profile of the ROLE  and attach it to the workspace cluster instance profile in advance setting
and also add it to user settings -> workspace admin -> securirty-> data security -> instance profile


##  Databricks Integration with AWS Glue Catalog

 Elevate the initial role created and add the Glue permission as well.
 >> spark.conf.set("spark.databricks.hive.metastore.glueCatalog.enabled", "true")
 >> spark.sql('show databases').show()
