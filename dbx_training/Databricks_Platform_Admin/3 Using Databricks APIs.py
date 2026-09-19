# Databricks notebook source
# MAGIC %md-sandbox
# MAGIC 
# MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC # Using Databricks APIs
# MAGIC 
# MAGIC In this lab you will learn how to:
# MAGIC * Authenticate and use Databricks REST APIs to remotely administer Databricks

# COMMAND ----------

# MAGIC %md
# MAGIC ##Prerequisites
# MAGIC 
# MAGIC If you would like to follow along with this lab, you will need:
# MAGIC * Ability to create new schemas in the *main* catalog (**`CREATE`** and **`USAGE`** privileges)
# MAGIC * Ability to create clusters (**`Allow unrestricted cluster creation`** entitlement)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Overview
# MAGIC 
# MAGIC Databricks exposes all its major functionality as a collection of REST APIs, whose documentation can be found <a href="https://docs.databricks.com/reference/api.html" target="_blank">here</a>.  Anything you can do in the user interface (and in some cases, things you can't even do in the user interface) can be done remotely using carefully constructed API calls. The Databricks CLI, as covered in the *Using Databricks Utilities and CLI* lab, uses REST APIs under the covers, as do automation frameworks like Terraform.
# MAGIC 
# MAGIC There are a number of ways to gain direct access to these APIs:
# MAGIC 
# MAGIC * Implement code that uses a low level web access API (like Python's **requests** module for example) to issue REST calls and interpret the results
# MAGIC * Use a client that provides low level web access (like **curl**, **wget** or **Postman**) to issue calls and view the results
# MAGIC 
# MAGIC When using a non-interactive client like **curl** or **wget**, users typically run the client in their own interactive shell environment. They may invoke commands manually or chain those commands into a higher-level script or automation framework of some sort. In this lab, we will take advantage of the execution environment provided by the attached all-purpose cluster for the purpose of demonstrating API usage with **curl**.
# MAGIC 
# MAGIC Regardless of which client you use, you need to include the following items with each call:
# MAGIC * The **URL** of the API endpoint you are calling, which is based on your Databricks instance. The endpoints are to be found in the documentation.
# MAGIC * The **HTTP method** to use in submitting the request, which depends on the endpoint and type of operation you are doing. For example, querying resources is done using **GET** while creating new resources is done with **POST**. Appropriate methods for each endpoint are to be found in the documentation.
# MAGIC * A **token** used to authenticate with the server. Though you can use a username and password to authenticate, it's recommended to use a bearer token instead.
# MAGIC 
# MAGIC Depending on the operation, you may need to specify additional data to fulfill the request.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup
# MAGIC 
# MAGIC As stated previously, we need a base URL for the APIs and a token for API authentication before we can proceed. Run the following cell to create a landing zone for the needed inputs, then follow the instructions below.

# COMMAND ----------

dbutils.widgets.text(name='url', defaultValue='')
dbutils.widgets.text(name='token', defaultValue='')

from urllib.parse import urlparse,urlunsplit

u = urlparse(dbutils.widgets.get('url'))

import os

os.environ["DBACADEMY_API_TOKEN"] = f"Authorization: Bearer {dbutils.widgets.get('token')}"
os.environ["DBACADEMY_API_URL"] = urlunsplit((u.scheme, u.netloc, f"/api/2.0", "", ""))

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's populate the two fields as follows.
# MAGIC 1. Go to <a href="#setting/account" target="_blank">User Settings</a> (which is also accessible from the left sidebar by selecting **Settings > User Settings**).
# MAGIC 1. Select the **Access tokens** tab.
# MAGIC 1. Click **Generate new token**.
# MAGIC     1. Specify a **Comment** such as *API Test*. Choose a short value for **Lifetime**; for the purpose of this lab, one or two days is sufficient.
# MAGIC     1. Click **Generate**.
# MAGIC     1. Copy the resulting token to the *token* field.
# MAGIC     1. Click **Done**.
# MAGIC 1. Copy the URL of your workspace (the contents of the address bar in your current browser session is sufficient) into the *url* field.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Exploring and managing the data hierarchy
# MAGIC 
# MAGIC Let's examine the data hierarchy beginning at the metastore level. First, let's list the metastores available. From the documentation of the Unity Catalog API, we must invoke the **listMetastores** endpoint using the **GET** method.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/metastores" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC This lists information about *all* metastores defined in the Databricks account governing this workspace. The following cell retrieves information regarding the metastore currently assigned to the workspace.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/metastore_summary" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's browse the structure within the currently assigned metastore, starting with the catalogs.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/catalogs" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC Notice that *hive_metastore* and *samples* are not listed, since these are not real catalogs. They are virtual entries mapped into the catalog namespace by Unity Catalog for convenient access to the local Hive metastore and Databricks sample datasets.
# MAGIC 
# MAGIC Now let's list the schemas within the catalog *main*. As per the documentation, the **`catalog_name`** parameter is required. For **GET** requests, parameters are encoded at the end of the URL.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/schemas?catalog_name=main" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's see the tables within the *default* schema of *main*. As per the documentation, the **`catalog_name`** and **`schema_name`** parameters are required.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/tables?catalog_name=main&schema_name=default" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC Now that we've browsed the data structures, let's create a new schema named *myschema_api* within the *main* catalog. This is a little different, since we must use **`POST`** to do this, which in turn requires us to specify JSON data using the **`-d`** option. Using a combination of shell features, we are inlining the JSON data below the command itself.
# MAGIC 
# MAGIC As per the documentation, the JSON data must specify:
# MAGIC * *name:* the name of the schema to create
# MAGIC * *catalog_name:* the name of the catalog in which to create the schema
# MAGIC 
# MAGIC Note that this will fail if you don't have appropriate privileges on *main*.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/schemas" -d @- | json_pp
# MAGIC {
# MAGIC   "name": "myschema_api",
# MAGIC   "catalog_name": "main"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC Open the **Data** page to validate the creation of the schema.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Exploring and managing workspace assets
# MAGIC 
# MAGIC So far we've used the APIs to browse and manage data assets, but it's also possible to automate the management of workspace assets and compute resources. As an example, let's create an all-purpose cluster. The parameters specified here are explained in the <a href="https://docs.databricks.com/api/latest/clusters.html#create" target="_blank">API documentation</a>, though you can also obtain sample JSON from the cluster creation UI as well.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/clusters/create" -d @- | json_pp
# MAGIC {
# MAGIC   "num_workers": 1,
# MAGIC   "cluster_name": "mycluster_api",
# MAGIC   "spark_version": "11.1.x-scala2.12",
# MAGIC   "node_type_id": "i3.xlarge",
# MAGIC   "autotermination_minutes": 120,
# MAGIC   "data_security_mode": "USER_ISOLATION",
# MAGIC   "runtime_engine": "STANDARD"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC Note the value for *cluster_id* from the output; we will need this shortly.
# MAGIC 
# MAGIC Now open the <a href="#setting/clusters" target="_blank">Compute</a> page (which is also accessible from the left sidebar) to validate the creation of the cluster.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup
# MAGIC 
# MAGIC Run the following cells to remove the resources we created throughout this lab. This further illustrates how APIs can be used to manage resources.
# MAGIC 
# MAGIC First, let's use an API to delete the schema we created.

# COMMAND ----------

# MAGIC %sh curl -s -X DELETE -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/unity-catalog/schemas/main.myschema_api"

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's call an API to delete the cluster we created. Note that you must subsitute the text *CLUSTER_ID* with the value of *cluster_id* from the cluster creation output.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/clusters/permanent-delete" -d @-
# MAGIC {
# MAGIC   "cluster_id": "CLUSTER_ID"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# MAGIC <br/>
# MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>