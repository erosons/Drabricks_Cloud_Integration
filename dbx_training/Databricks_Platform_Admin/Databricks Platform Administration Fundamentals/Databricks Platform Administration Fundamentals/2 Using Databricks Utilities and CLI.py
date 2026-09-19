# Databricks notebook source
# MAGIC %md-sandbox
# MAGIC 
# MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC # Using Databricks Utilities and CLI
# MAGIC 
# MAGIC In this lab you will learn how to:
# MAGIC * Use Databricks utilities (**dbutils**) to perform various tasks from within your notebooks
# MAGIC * Install, configure and use the Databricks CLI to remotely administer Databricks

# COMMAND ----------

# MAGIC %md
# MAGIC ##Prerequisites
# MAGIC 
# MAGIC If you would like to follow along with this lab, you will need access to a cluster with *Single user* access mode. The *Shared* access mode does not support the operations required by this lab.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Databricks Utilities
# MAGIC 
# MAGIC **dbutils** is a collection of utility functions that empowers you to do more within your notebooks, making it easy to perform powerful combinations of tasks. You can use the utilities to work with object storage efficiently, chain and parametrize notebooks, and to work with secrets. dbutils are only available in the context of a notebook and have Python, R and Scala bindings.
# MAGIC 
# MAGIC In this lab, we will explore usage using Python. Refer to the <a href="https://docs.databricks.com/dev-tools/databricks-utils.html" target="_blank">documentation</a> for other languages.
# MAGIC 
# MAGIC For starters, let's invoke the online help to see available commands.

# COMMAND ----------

dbutils.help()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Parametrizing notebooks with widgets
# MAGIC 
# MAGIC Let's look at an example usage of dbutils: creating input widgets that allow you to add parameters to your notebooks and dashboards. Let's try a simple example that creates a text input field named *token*.

# COMMAND ----------

dbutils.widgets.text(name='token', defaultValue='')

# COMMAND ----------

# MAGIC %md
# MAGIC #### Widgets in Python applications
# MAGIC 
# MAGIC As of DBR 11.0, Databricks recommends using **ipywidgets** for interactive widgets in Python applications. **ipywidgets** provides a broader suite of widgets with a richer programming interface.
# MAGIC 
# MAGIC In this lab, we'll stick to Databricks widgets, but for the sake of illustration, the code below exemplifies usage that is roughly equivalent to what we're doing here:
# MAGIC ```
# MAGIC import ipywidgets as w
# MAGIC token_widget = w.Text(description='Token:')
# MAGIC token_widget
# MAGIC ```
# MAGIC The input value can be retrieved as follows:
# MAGIC ```
# MAGIC token_widget.value
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ### Accessing DBFS
# MAGIC 
# MAGIC Let's look at another example usage of dbutils: accessing and managing DBFS (Databricks File System). DBFS is a distributed file system mounted into a Databricks workspace and available on all Databricks clusters associated with that workspace. DBFS is an abstraction on top of scalable object storage that provides an optimized interface that maps to native cloud storage API calls. It's peristent, unlike the ephemeral file systems that clusters use, and provides a convenient location for exchanging information between the workspace and running clusters.
# MAGIC 
# MAGIC Let's access the online help for the **`fs`** command.

# COMMAND ----------

dbutils.fs.help()

# COMMAND ----------

# MAGIC %md
# MAGIC #### Reading from DBFS
# MAGIC 
# MAGIC Now let's invoke the **`fs`** command to display the contents of the topmost folder in DBFS. Wrapping this into a call to **`display()`** nicely formats it as a table.

# COMMAND ----------

display(dbutils.fs.ls("/"))

# COMMAND ----------

# MAGIC %md
# MAGIC #### Creating a file in DBFS
# MAGIC 
# MAGIC Let's create a file in DBFS, */tmp/token* (overwriting, if needed) that contains the value specified in the widget we created earlier.

# COMMAND ----------

dbutils.fs.put('/tmp/token', dbutils.widgets.get('token'), True)

# COMMAND ----------

# MAGIC %md
# MAGIC Before proceeding, create a personal access token and paste its value into the *token* widget.
# MAGIC 1. Go to <a href="#setting/account" target="_blank">User Settings</a> (which is also accessible from the left sidebar by selecting **Settings > User Settings**).
# MAGIC 1. Select the **Access tokens** tab.
# MAGIC 1. Click **Generate new token**.
# MAGIC     1. Specify a **Comment** such as *CLI Test*. Choose a short value for **Lifetime**; for the purpose of this lab, one or two days is sufficient.
# MAGIC     1. Click **Generate**.
# MAGIC     1. Copy the resulting token to the clipboard and click **Done**.
# MAGIC 1. Paste the generated token into the *token* widget and proceed.
# MAGIC 
# MAGIC Default widget behavior will automatically trigger the execution of any cell that references the widget's value; thus the */tmp/token* file will automatically be rewritten after you paste the token.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Databricks command-line interface
# MAGIC 
# MAGIC The Databricks command-line interface (CLI) enables you to automate tasks through an easy-to-use interface to the Databricks platform. Built on top of the Databricks REST APIs, Databricks CLI is organized into command groups allowing you to perform a variety of tasks.
# MAGIC 
# MAGIC Users typically install and run the client in their own environment, where they can invoke commands manually or integrate the CLI with an automation framework of some sort. The CLI is implemented in Python and can be used from any shell-based environment that has Python support (2.7.9+ or 3.7+).
# MAGIC 
# MAGIC In this lab, we will take advantage of the execution environment provided by the attached all-purpose cluster for the purpose of demonstrating installation and usage.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Installing the CLI
# MAGIC 
# MAGIC Let 's install the CLI using **`pip`**. Please note the following peculiarites that relate to performing this on a Databricks cluster using a notebook:
# MAGIC 
# MAGIC * We precede the actual command with the **`%sh`** magic command to run it in a command-line shell on the cluster. In a conventional shell environment, this would not be necessary and we would simply issue the **`pip install`** command directly.
# MAGIC * The resulting software is installed as part of an ephemeral execution environment. You will need to reinstall and reconfigure the CLI if the cluster is restarted, or even if you simply reattach to it. In a conventional environment, the installation and configuration would be persistent.

# COMMAND ----------

# MAGIC %sh pip install databricks-cli

# COMMAND ----------

# MAGIC %md
# MAGIC Let's perform a basic test of the installation by invoking the **`databricks`** command. Once again, we need to precede the command with the **`%sh`** magic command since we are running this in the context of a notebook cell.

# COMMAND ----------

# MAGIC %sh databricks --help

# COMMAND ----------

# MAGIC %md
# MAGIC ### Configuring the CLI
# MAGIC 
# MAGIC Before we can run any commands that interact with the Databricks environment, we need to configure the CLI, which sets up authentication. Let's review the options available.

# COMMAND ----------

# MAGIC %sh databricks configure --help

# COMMAND ----------

# MAGIC %md
# MAGIC Let's configure the CLI now by specifying the URL of our workspace and a personal access token as authentication credentials.
# MAGIC 
# MAGIC Before running this cell, replace the string *URL* with the URL of your workspace, stripping off the path (that is, everything after the host).
# MAGIC 
# MAGIC For the token, we're using the file created earlier in conjunction with the **`--token-file`** option. When running this in an interactive shell environment, you would have the option using the **`--token`** option and specifying the token interactively.

# COMMAND ----------

# MAGIC %sh databricks configure --host URL --token-file /dbfs/tmp/token

# COMMAND ----------

# MAGIC %md
# MAGIC With this simple configuration complete, you can now begin managing your Databricks environment through the CLI. Note that in this lab we are administering the current workspace, though we can administer any workspace this way with the appropriate URL and token generated from that workspace.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Using the CLI
# MAGIC 
# MAGIC The CLI essentially provides an interface to the APIs that's easy to use from a command-line shell. Not all of the APIs are covered, but there's a lot you can do with the command-line interface, and we're only going to scratch the surface here. For a full discourse on all the options available, refer to the <a href="https://docs.databricks.com/dev-tools/cli/index.html" target="_blank">documentation</a>.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Exploring and managing the data hierarchy
# MAGIC 
# MAGIC Let's examine the data hierarchy beginning at the metastore level. First, let's list the metastores available.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog metastores list

# COMMAND ----------

# MAGIC %md
# MAGIC This lists information about *all* metastores defined in the Databricks account governing this workspace. The following cell retrieves information regarding the metastore currently assigned to the workspace.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog metastores get-summary

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's browse the structure within the currently assigned metastore, starting with the catalogs.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog catalogs list

# COMMAND ----------

# MAGIC %md
# MAGIC Notice that *hive_metastore* and *samples* are not listed, since these are not real catalogs. They are virtual entries mapped into the catalog namespace by Unity Catalog for convenient access to the local Hive metastore and Databricks sample datasets.
# MAGIC 
# MAGIC Now let's list the schemas within the catalog *main*.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog schemas list --catalog-name main

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's see the tables within the *default* schema of *main*.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog tables list --catalog-name main --schema-name default

# COMMAND ----------

# MAGIC %md
# MAGIC Now that we've browsed the data structures, let's create a new schema named *myschema_cli* within the *main* catalog. Note that this will fail if you don't have appropriate privileges on *main*.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog schemas create --catalog-name main --name myschema_cli

# COMMAND ----------

# MAGIC %md
# MAGIC Open the **Data** page to validate the creation of the schema.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Exploring and managing workspace assets
# MAGIC 
# MAGIC So far we've used the CLI to browse and manage data assets, but it's also possible to automate the management of workspace assets and compute resources through the CLI. As an example, let's use the CLI to create an all-purpose cluster. Let's first take a look at the options available.

# COMMAND ----------

# MAGIC %sh databricks clusters create --help

# COMMAND ----------

# MAGIC %md
# MAGIC Let's create a JSON file in DBFS to describe the cluster configuration. The parameters specified herre are explained in the <a href="https://docs.databricks.com/api/latest/clusters.html#create" target="_blank">API documentation</a>, though you can also obtain sample JSON from the cluster creation UI as well.
# MAGIC 
# MAGIC Note that the configuration file is not strictly necessary; the **`--json`** option allows us to specify JSON inline, however this is cumbersome to use so we use a file instead.

# COMMAND ----------

dbutils.fs.put(
    "/tmp/cluster.json",
    """{
        "num_workers": 1,
        "cluster_name": "mycluster_cli",
        "spark_version": "11.1.x-scala2.12",
        "node_type_id": "i3.xlarge",
        "autotermination_minutes": 120,
        "data_security_mode": "USER_ISOLATION",
        "runtime_engine": "STANDARD"
    }""",
    True)

# COMMAND ----------

# MAGIC %md
# MAGIC With the configuration file in place, let's create the cluster.

# COMMAND ----------

# MAGIC %sh databricks clusters create --json-file /dbfs/tmp/cluster.json

# COMMAND ----------

# MAGIC %md
# MAGIC Note the value for *cluster_id*; we will need this shortly.
# MAGIC 
# MAGIC Now open the <a href="#setting/clusters" target="_blank">Compute</a> page (which is also accessible from the left sidebar) to validate the creation of the cluster.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup
# MAGIC 
# MAGIC Run the following cells to remove the resources we created throughout this lab. This further illustrates how dbtuils and CLI can be used to manage resources.

# COMMAND ----------

# MAGIC %md
# MAGIC First, let's clean up the DBFS files.

# COMMAND ----------

dbutils.fs.rm("/tmp/cluster.json")
dbutils.fs.rm("/tmp/token")

# COMMAND ----------

# MAGIC %md
# MAGIC Let's use the CLI to delete the schema we created.

# COMMAND ----------

# MAGIC %sh databricks unity-catalog schemas delete --full-name main.myschema_cli

# COMMAND ----------

# MAGIC %md
# MAGIC Finally, let's use the CLI to delete the cluster we created. Note that you must subsitute the text *CLUSTER_ID* with the actual cluster id, which was output from the cluster create command earlier. Let's perform that substitution, then run the cell.

# COMMAND ----------

# MAGIC %sh databricks clusters permanent-delete --cluster-id "CLUSTER_ID"

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# MAGIC <br/>
# MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>