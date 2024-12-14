# %sql
# -- Databricks notebook source
# -- MAGIC %md-sandbox
# -- MAGIC 
# -- MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# -- MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# -- MAGIC </div>

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC # Building and Automating a Data Pipeline
# -- MAGIC 
# -- MAGIC In this notebook we will set up a simple collection of tables modelled in the Delta architecture. The main purpose of the exercise is to provide a baseline approach for illustrating how this sort of thing can be done. Then we'll look at some alternate approaches for achieving the same end goal.
# -- MAGIC 
# -- MAGIC The result will consist of the following collection of tables:
# -- MAGIC * A bronze table that materializes a temporary view created against a CSV file living in cloud storage
# -- MAGIC * A silver table representing the bronze table with a cleaned up schema and basic standardization of the column values
# -- MAGIC * A couple gold tables performing various aggregations against the silver table
# -- MAGIC 
# -- MAGIC The dataset is provided as part of the collection of Databricks sample datasets and contains information related to movie productions.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ## Prerequisites
# -- MAGIC If you would like to follow along with this notebook, you will need:
# -- MAGIC * **USAGE** and **CREATE** permissions on the *main* catalog. If you have access to a differently named catalog, then update the value for *catalog* (see below) before proceeding to run the setup cells
# -- MAGIC * Workspace admin capabilities

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ## Setup
# -- MAGIC 
# -- MAGIC Run the following cells to perform some setup. Let's first create fields for specifying the *catalog* and *schema*. If this notebook is run non-interactively, these parameters are to be specified in the invocation in order to override the defaults.

# -- COMMAND ----------

# -- MAGIC %python
# -- MAGIC dbutils.widgets.text(name="catalog", defaultValue="main")
# -- MAGIC dbutils.widgets.dropdown("schema", "dev", ["dev", "staging", "prod"])

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC If you need to use a catalog other than *main* then specify that now in the field above.
# -- MAGIC 
# -- MAGIC Now let's invoke a helper script that will create a uniquely named schema for us to use within the specified catalog. It will also set a default catalog and schema to make references easier.

# -- COMMAND ----------

# -- MAGIC %run ./Includes/Create-Delta-Architecture-setup

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ## Building a data pipeline using traditional notebook constructs
# -- MAGIC 
# -- MAGIC In this section, we'll work through a simple example of a Delta architecture pipeline, built using traditional notebook constructs. This will additionally provide some explanation behind the example before we look at improved methods to deploy this pipeline.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Ingesting into the bronze layer
# -- MAGIC 
# -- MAGIC Databricks provides a number of sample datasets available via DBFS and Unity Catalog. In this case, we will ingest a CSV from cloud storage (originally found in the DBFS sample datasets) containing information related to movie productions, and construct a temporary view to query the data. In a real life scenario this step would likely be replaced with a real data source (batch or streaming) using Autoloader or COPY INTO for idempotent incremental ETL.

# -- COMMAND ----------

# -- MAGIC %python
# -- MAGIC spark.read.format('csv') \
# -- MAGIC   .option("header", "true") \
# -- MAGIC   .option("sep", ",") \
# -- MAGIC   .load('wasbs://courseware@dbacademy.blob.core.windows.net/ci_cd_administration_in_databricks/v01/rdatasets/data-001/csv/ggplot2/movies.csv') \
# -- MAGIC   .createOrReplaceTempView('temp_bronze_movies')

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC Let's materialize the view into a table called *bronze_movies*. Here we are just capturing data in its raw form; no transformation are taking place at all.

# -- COMMAND ----------

# CREATE OR REPLACE TABLE bronze_movies
#   AS SELECT * FROM temp_bronze_movies

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Creating the silver layer
# -- MAGIC 
# -- MAGIC In the bronze layer, the schema is a little sloppy and contains extraneous information, and the data itself poses challenges for optimal downstream querying. So we'll clean all this up in the silver layer. Specifically we'll do the following:
# -- MAGIC * Assign the name *idx* to the first column
# -- MAGIC * Cast *year* and *length* as **`INT`**
# -- MAGIC * Cast *budget* as **`INT`**, specifying 0 where the value was previously *NA*
# -- MAGIC * Cast *rating* as **`DOUBLE`**
# -- MAGIC * Cast *votes* as **`INT`**
# -- MAGIC * Replace *null* in the *mpaa* column with *NR*
# -- MAGIC * Cast all the genre columns to **`BOOLEAN`**
# -- MAGIC 
# -- MAGIC Also we'll omit the columns *r1* through *r10* as our downstream processing will have no use for them.

# -- COMMAND ----------

# CREATE OR REPLACE TABLE silver_movies
# AS SELECT
#   _c0 AS idx,
#   title,
#   CAST(year AS INT) AS year,
#   CAST(length AS INT) AS length,
#   CASE WHEN
#     budget = 'NA' THEN 0
#     ELSE CAST(budget AS INT)
#   END AS budget,
#   CAST(rating AS DOUBLE) AS rating,
#   CAST(votes AS INT) AS votes,
#   CASE WHEN
#     mpaa is null THEN 'NR'
#     ELSE mpaa
#   END AS mpaa,
#   CAST(Action AS BOOLEAN) AS Action,
#   CAST(Comedy AS BOOLEAN) AS Comedy,
#   CAST(Drama AS BOOLEAN) AS Drama,
#   CAST(Documentary AS BOOLEAN) AS Documentary,
#   CAST(Romance AS BOOLEAN) AS Romance,
#   CAST(Short AS BOOLEAN) AS Short
# FROM bronze_movies

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Creating the gold layer
# -- MAGIC 
# -- MAGIC In the gold layer, let's create a couple tables to provide some interesting aggregations:
# -- MAGIC * *gold_average_budget_by_year* to track average spend per production over the years
# -- MAGIC * *gold_movies_made_by_year* to track total number of productions per year over the years

# -- COMMAND ----------

# CREATE OR REPLACE TABLE gold_average_budget_by_year
# AS SELECT
#   year,
#   AVG(budget) AS average_budget
# FROM silver_movies
# WHERE budget > 0
# GROUP by year
# ORDER BY year

# -- COMMAND ----------

# CREATE OR REPLACE TABLE gold_movies_made_by_year
# AS SELECT
#   year,
#   COUNT(year) AS movies_made
# FROM silver_movies
# GROUP by year
# ORDER BY year

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Viewing the results
# -- MAGIC 
# -- MAGIC Prior to advancing, let's observe the results. For best results, try visualizing the table using a line graph or similar representation.

# -- COMMAND ----------

# SELECT * FROM gold_average_budget_by_year

# -- COMMAND ----------

# SELECT * FROM gold_movies_made_by_year

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ## Automation using a pipeline
# -- MAGIC 
# -- MAGIC So far in this notebook, we've worked through the steps of building a data pipeline modelled in the Delta architecture, but this approach doesn't scale particularly well, nor does it lend itself to easily automating updates since the setup is tied with data updates.
# -- MAGIC 
# -- MAGIC In this section we'll adopt an updated and simplified approach using Delta Live Tables, driving the automation with Databricks workflows.
# -- MAGIC 
# -- MAGIC For the sake of comparison, refer to <a href="$./3 Delta Architecture Pipeline" target="_blank">this notebook</a> that illustrates a Python reimplementation of what we've done here using Delta Live Tables.
# -- MAGIC 
# -- MAGIC Before proceeding, let's run the following cell to obtain the value we'll need to specify for **Target** parameter when creating the pipeline.

# -- COMMAND ----------

# SELECT "${da.schema}" AS Target

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Creating the pipeline
# -- MAGIC 
# -- MAGIC Let's create a pipeline - conceptually, the Delta Live Tables equivalent of a job - that will execute the notebook referenced above. Note, Delta Live Tables notebooks can only be executed in a pipeline; they cannot be executed interactively.
# -- MAGIC 
# -- MAGIC 1. In the **Workflows** page, select the **Delta Live Tables** tab.
# -- MAGIC 1. Click **Create Pipeline**.
# -- MAGIC 1. Specify a pipeline name.
# -- MAGIC 1. For **Notebook libaries**, use the navigator to locate and select <a href="$./4 Delta Architecture Pipeline" target="_blank">this notebook</a>, the pipeline implementation of the Delta architecture we created in the previous section.
# -- MAGIC 1. For **Target**, specify the value output from the cell above. This will publish the tables to the specified schema in the *hive_metastore* catalog.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Manually triggering an update
# -- MAGIC 
# -- MAGIC With a pipeline created we can trigger it on demand. Let's try that now.
# -- MAGIC 
# -- MAGIC 1. With *Development* mode selected, let's run an update by clicking **Start**.
# -- MAGIC 1. The initial update will take a few moments since a cluster needs to be provisioned. Once this happens though, future iterations will be quicker with *Development* mode selected, since it can reuse the same cluster (if it's still around and runnning).

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC #### Viewing the results
# -- MAGIC 
# -- MAGIC Let's take a look at the results that live in the schema specified by **Target** in the *hive_metastore* catalog.

# -- COMMAND ----------

# SELECT * FROM hive_metastore.${da.schema}.gold_average_budget_by_year

# -- COMMAND ----------

# SELECT * FROM hive_metastore.${da.schema}.gold_movies_made_by_year

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ### Automating pipeline updates
# -- MAGIC 
# -- MAGIC Let's prepare to automate the periodic update of this pipeline. At a high level, this process involves:
# -- MAGIC * Creating a job to periodically update the pipeline. This doesn't have to be a complicated job; in fact it can be as simple as one single task.
# -- MAGIC * Establishing a service principal to run this job. In keeping with administrative best practices, service principals should always be used for jobs that will be run on an ongoing basis.
# -- MAGIC * Updating the ownerships of the job and pipeline to run as the service principal.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC #### Creating a job to update the pipeline
# -- MAGIC 
# -- MAGIC Though we can define new jobs from the **Jobs** tab of the **Workspaces** page, a shortcut is provided in the pipeline page for this.
# -- MAGIC 
# -- MAGIC 1. In the pipeline page for the pipeline we just created, let's click **Schedule**.
# -- MAGIC 1. Let's fill in a name, configure the desired schedule, then click **Create**.
# -- MAGIC 
# -- MAGIC This shortcut creates a single-task job with the specified name that triggers an update of this pipeline on the specified schedule. We can validate that this exists as job in the **Jobs** tab of the **Workflows** page.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC #### Creating a service principal
# -- MAGIC 
# -- MAGIC As mentioned, administrative best practices advocate running ongoing jobs as a service principal. In a real world scenario, you may already have one set up for this purpose, but for this training exercise let's create one now like we did in the *Managing Identities in the Workspace* lab.
# -- MAGIC 
# -- MAGIC 1. In the admin console, let's click the **Service principals** tab.
# -- MAGIC 1. Click **Add service principal**.
# -- MAGIC 1. Select **Add new service principal**.
# -- MAGIC 1. Specify a unique name and click **Add**.
# -- MAGIC 1. Select the newly created service principal to enable the **Allow cluster creation** entitlement.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC #### Adjusting ownerships
# -- MAGIC 
# -- MAGIC Now have a service principal identity for the purpose of running the pipeline, let's configure ownership of the job and pipeline to run as the service principal.
# -- MAGIC 
# -- MAGIC 1. In the **Jobs** tab of the **Workspaces** page, let's select the job we created.
# -- MAGIC 1. Let's click **Permissions**.
# -- MAGIC 1. Let's remove the existing *Is Owner* permission and add a new one. For the **NAME**, let's choose the service principal.
# -- MAGIC 1. Let's save our changes.
# -- MAGIC 
# -- MAGIC Now we need to repeat this procedure for the pipeline itself.
# -- MAGIC 1. In the **Delta Live Tables** tab of the **Workspaces** page, let's select the pipeline we created a moment ago.
# -- MAGIC 1. Let's click **Edit permissions**.
# -- MAGIC 1. Once again let's remove the existing *Is Owner* permission and add a new one for the service principal. For the **NAME**, let's choose the service principal.
# -- MAGIC 1. Let's save our changes.
# -- MAGIC 
# -- MAGIC NOTE: you will need to ensure that the service principal has appropriate permissions to run the notebook.
# -- MAGIC * If the notebook lives in a Repo, provide *Can Read* permission on the Repo
# -- MAGIC * If the notebook lives in the workspace, provide *Can Read* permission on the notebook
# -- MAGIC 
# -- MAGIC From here on in, the job and associated pipeline will run on the specified schedule as the service principal we established. You can test it out by visiting the job's page and clicking **Run now**.

# -- COMMAND ----------

# -- MAGIC %md
# -- MAGIC ## Clean up
# -- MAGIC Run the following cell to remove the resources that we created in this lab.

# -- COMMAND ----------

# -- MAGIC %python
# -- MAGIC da.cleanup()

# -- COMMAND ----------

# -- MAGIC %md-sandbox
# -- MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# -- MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# -- MAGIC <br/>
# -- MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>
