# Databricks notebook source
# MAGIC %md-sandbox
# MAGIC 
# MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC # Using Terraform with Databricks
# MAGIC 
# MAGIC In this lab you will learn how to:
# MAGIC * Install and configure open source Terraform
# MAGIC * Remotely administer Databricks using open source Terraform and Terraform Cloud

# COMMAND ----------

# MAGIC %md
# MAGIC ##Prerequisites
# MAGIC 
# MAGIC If you would like to follow along with this lab, you will need access to a cluster with *Single user* access mode. The *Shared* access mode does not support the operations required by this lab.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Overview
# MAGIC 
# MAGIC Terraform is a software tool that allows you to define infrastructure as code. Terraform integrates with hundreds of upstream APIs including Databricks. Most of the resources exposed by Databricks APIs can be managed with Terraform.
# MAGIC 
# MAGIC Terraform is accessible in two ways:
# MAGIC * A free, open source self-managed tool available in binary form that can be run in a variety of operating systems
# MAGIC * A managed SaaS platform known as **Terraform Cloud** that offers free and paid tiers
# MAGIC 
# MAGIC We will explore both options in this lab, but we'll starting with the self-managed version. During that time, we'll also get acquainted with the constructs of a Terraform environment and its operation, before seeing how it all fits in with Terraform Cloud.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Open source Terraform
# MAGIC 
# MAGIC Hashicorp offers a completely free version of Terraform that you download and manage on your own. Users typically install it in their own environment, where they can invoke it manually or integrate it with upstream CI/CD processes. In this lab, we will take advantage of the execution environment provided by the attached all-purpose cluster for the purpose of demonstrating installation and usage.
# MAGIC 
# MAGIC When managing Terraform on your own, there's a couple important considerations to keep in mind. The details of these fall outside the scope of this lab, but we mention them here so that you will be aware of them if you choose to go down this route.
# MAGIC 
# MAGIC * **Configuration files:** Terraform configurations are defined by a collection of text files written in Terraform language. Since this is infrastructure as code, these files should be treated like any other code. It's definitely a good idea to manage them using revision control.
# MAGIC * **Authentication:** because Terraform uses Databricks APIs, it needs authentication credentials. If you happen to be using the Databricks CLI in the same environment, Terraform can use its authentication setup. Otherwise, environment variables are generally considered the safest option. As a final resort, credentials can be embedded in the configuration files themselves, but be careful with this since it's easy to inadvertently distribute to others directly or through revision control.
# MAGIC * **State management:** Terraform tracks and records the current state of the system using a *backend*, and this part is crucial for Terraform to function correctly and reliably. The backend storage must be persistent (at least for the life of the resources it manages) and accessible by all who may be managing the configuration.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Setup
# MAGIC 
# MAGIC Before we begin we need to perform some setup, first to install the tool itself, then to begin setting up a Terraform environment.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Installing Terraform
# MAGIC 
# MAGIC Terraform Open Source is available from the <a href="https://www.terraform.io/downloads" target="_blank">downloads page</a> and is offered in a number of formats to accomodate most mainstream operating systems. For this lab, however, we will simply download the raw binary and install it manually. Note that we are downloading version 1.2.8, which was the most current version at the time of this writing. We'll use **`wget`** to download the archive and stash it in the */tmp* directory of the cluster file system.

# COMMAND ----------

# MAGIC %sh wget -P /tmp https://releases.hashicorp.com/terraform/1.2.8/terraform_1.2.8_linux_amd64.zip

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's extract the binary to our ephemeral execution environment. Because this environment is temporary, you will need to reinstall if the cluster is restarted, or even if you simply reattach to it. In a conventional environment, users would typically install to a persistent area of the file system.

# COMMAND ----------

# MAGIC %sh unzip -d $VIRTUAL_ENV/bin /tmp/terraform_1.2.8_linux_amd64.zip 

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's perform a basic test of the installation by invoking the **`terraform`** command.

# COMMAND ----------

# MAGIC %sh terraform -v

# COMMAND ----------

# MAGIC %md
# MAGIC #### Configuring authentication
# MAGIC 
# MAGIC There are three different ways to configure authentication for open source Terraform.
# MAGIC 
# MAGIC The first option is to specify the credentials as parameters in a configuration file. This is easy to set up (and for this reason, it's the method we'll use in this lab), but in a production system you need to be very careful about embedding authentication credentials in your configuration files since it's easy to accidentally leak them, either directly or by checking them in to revision control. Also, since the credentials become part of that configuration, they will not be available to other configurations.
# MAGIC 
# MAGIC The other two methods are safer in general, and have global effect (that is, they will be inherited by all configurations being managed by Terraform in that environment):
# MAGIC * Configure the Databricks CLI like we did in the lab *Using Databricks Utilities and CLI*. Terraform will use this setup to authenticate by default.
# MAGIC * Set up the environment variables *DATABRICKS_HOST* and *DATABRICKS_TOKEN*, which Terraform also checks when authenticating.
# MAGIC 
# MAGIC To begin, let's create landing zones to specify the workspace URL and token. 

# COMMAND ----------

dbutils.widgets.text(name='token', defaultValue='')
dbutils.widgets.text(name='url', defaultValue='')

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's establish a Terraform configuration in the */terraform* folder of DBFS and write the authentication credentials to configuration file within named *databricks.tf*.
# MAGIC 
# MAGIC Once again, while this approach is simple for the purpose of a training exercise,  hardcoding authentication information like this in a configuration file is not considered best practice in a production environment. Consider instead using variables that allow you to define the actual values elsewhere, or configuring authentication using the Databricks CLI or environment variables.

# COMMAND ----------

dbutils.fs.put(
    "/terraform/databricks.tf",
    f"""
    provider databricks {{
        host  = "{dbutils.widgets.get('url')}"
        token = "{dbutils.widgets.get('token')}"
    }}
    """,
    True)

# COMMAND ----------

# MAGIC %md
# MAGIC Before we go any further, let's supply the needed authentication information.
# MAGIC 
# MAGIC First, create a personal access token and paste its value into the *token* widget.
# MAGIC 1. Go to <a href="#setting/account" target="_blank">User Settings</a> (which is also accessible from the left sidebar by selecting **Settings > User Settings**).
# MAGIC 1. Select the **Access tokens** tab.
# MAGIC 1. Click **Generate new token**.
# MAGIC     1. Specify a **Comment** such as *Terraform Test*. Choose a short value for **Lifetime**; for the purpose of this lab, one or two days is sufficient.
# MAGIC     1. Click **Generate**.
# MAGIC     1. Copy the resulting token to the clipboard and click **Done**.
# MAGIC 1. Paste the generated token into the *token* widget.
# MAGIC 
# MAGIC Now, supply the *url* value by copying the address of the workspace, stripping off the path component.
# MAGIC 
# MAGIC Whenever you update the values of these widgets, the file will be automatically updated.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Configuring the provider
# MAGIC 
# MAGIC Next, we'll need to specify information for Terraform to be able to look up the Databricks *provider* (that is, the Terraform plugin that integrates with Databricks).
# MAGIC 
# MAGIC We're also going to configure the backend to use the */tmp* area of the cluster file system. This would be a terrible choice in a production environment, but for the purpose of a training lab it's sufficent and convenient. In a production system, seriously consider using a remote backend as documented <a href="https://www.terraform.io/language/settings/backends/configuration" target="_blank">here</a>.

# COMMAND ----------

dbutils.fs.put(
    "/terraform/terraform.tf",
    """
    terraform {
        required_providers {
            databricks = {
                source  = "databricks/databricks"
                version = "1.0.1"
            }
        }
        backend "local" {
            path = "/tmp/terraform/terraform.tfstate"
        }
    }
    """,
    True)

# COMMAND ----------

# MAGIC %md
# MAGIC #### Initializing Terraform
# MAGIC With all the basic structure in place, let's initialize this configuration using Terraform's **`init`** command. This triggers the download of additional software bits needed to support the configuration (in this case, the Databricks provider) and sets up an initial state. Once that's complete we are ready to start defining our system and actually using Terraform to build it. 

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform init

# COMMAND ----------

# MAGIC %md
# MAGIC ### Declaring a new schema
# MAGIC 
# MAGIC For those who followed along with the labs *Using Databricks Utilities and CLI* and *Using Databricks APIs*, let's work toward definined a Terraform configuration that builds the elements that we created in those labs. As a first step, let's establish a new schema in the *main* catalog named *myschema_tfos*.
# MAGIC 
# MAGIC To add elements to a Terraform configuration, we can simply add an arbitrarily named **`.tf`** file to the folder. In this case we will simply add the file *schema.tf* to specify the schema.
# MAGIC 
# MAGIC Terraform configuration files are written in the Terraform language, which is built on a simple, declarative syntax. The configuration files describe the desired state of the system, which makes defining and managing the system extremely easy for an admin since Terraform manages all the changes needed to get the system to the desired state.
# MAGIC 
# MAGIC Because we're running this in the context of a notebook, there's some extra code wrapped around the actual configuration; the essence of the configuration is found within the triple-quotation fences. The actual configuration reads:
# MAGIC 
# MAGIC     resource "databricks_schema" "myschema" {
# MAGIC         catalog_name = "main"
# MAGIC         name         = "myschema_tfos"
# MAGIC         comment      = "This schema is managed by Terraform Open Source"
# MAGIC     }

# COMMAND ----------

dbutils.fs.put(
    "/terraform/schema.tf",
    """
    resource "databricks_schema" "myschema" {
        catalog_name = "main"
        name         = "myschema_tfos"
        comment      = "This schema is managed by Terraform Open Source"
    }
    """,
    True)

# COMMAND ----------

# MAGIC %md
# MAGIC ####Examining the plan
# MAGIC 
# MAGIC To get the system to the desired state, Terraform analyzes the current state of the system, compares it with the desired state as defined in the configuration files, and builds a plan to get it there. Terraform's **`plan`** command allows us to review the proposed changes without actually effecting them. Let's try that now.

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform plan

# COMMAND ----------

# MAGIC %md
# MAGIC This displays a summary of the actions Terraform will take if we applied the plan. This gives us the opportunity to do a sanity check, and can be a big timesaver when dealing with large and complex systems. Here we see that a new schema will be created.

# COMMAND ----------

# MAGIC %md
# MAGIC ####Applying the plan
# MAGIC 
# MAGIC Once satisfied with the plan, let's now run the **`apply`** command to effect the changes. Here we use the **`-auto-approve`** option since we are running the command in a non-interactive shell and therefore do not want to be prompted to confirm.
# MAGIC 
# MAGIC And now, a quick note about atomicity: in a dynamic production environment, be aware that when viewing and applying a plan in separate steps, there is a potential for the plan to change in the time in between. Terraform does issue a notification to this effect, with instructions on how to deal with this situation.
# MAGIC 
# MAGIC In a constrained environment like this where no one else is interacting with the system, we don't have to worry too much about atomicity.

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform apply -auto-approve

# COMMAND ----------

# MAGIC %md
# MAGIC Once this completes, open the **Data** page to validate the creation of the schema.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Declaring a compute resource
# MAGIC 
# MAGIC Now let's add a cluster to our desired configuration in a new file, *cluster.tf*. The configuration looks like this:
# MAGIC 
# MAGIC     resource "databricks_cluster" "mycluster" {
# MAGIC         num_workers = 1
# MAGIC         cluster_name = "mycluster_tfos"
# MAGIC         idempotency_token = "mycluster_tfos"
# MAGIC         spark_version = "11.1.x-scala2.12"
# MAGIC         node_type_id = "i3.xlarge"
# MAGIC         autotermination_minutes = 120
# MAGIC         data_security_mode = "USER_ISOLATION"
# MAGIC     }
# MAGIC 
# MAGIC If you followed along with the lab *Using Databricks APIs*, I will draw your attention to three things:
# MAGIC * We are describing a cluster with an identical configuration to that used in the lab, differing only by the name
# MAGIC * The parameter names used in Terraform are designed to match with those defined by the corresponding API
# MAGIC * We introduce an additional parameter, *idempotency_token*. This parameter is used by Terraform to uniquely identify the cluster it created, since *cluster_name* does not have to be unique and is thus not sufficient for this purpose

# COMMAND ----------

dbutils.fs.put(
    "/terraform/cluster.tf",
    """
    resource "databricks_cluster" "mycluster" {
        num_workers = 1
        cluster_name = "mycluster_tfos"
        idempotency_token = "mycluster_tfos"
        spark_version = "11.1.x-scala2.12"
        node_type_id = "i3.xlarge"
        autotermination_minutes = 120
        data_security_mode = "USER_ISOLATION"
    }
    """,
    True)

# COMMAND ----------

# MAGIC %md
# MAGIC ####Examining the plan
# MAGIC 
# MAGIC Once again, let's view the plan first.

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform plan

# COMMAND ----------

# MAGIC %md
# MAGIC We see that Terraform plans to create the cluster, but has no plans to do anything with the schema since nothing has changed with it since the last apply.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Applying the plan
# MAGIC 
# MAGIC Now let's apply the plan. Note that this operation is synchronous, and so it will take some time while it waits for the cluster to be created.

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform apply -auto-approve

# COMMAND ----------

# MAGIC %md
# MAGIC #### Making changes
# MAGIC 
# MAGIC We've seen how Terraform applies changes incrementally; this is, it examines the current state of the system, compares it with the desired state, and factors out items that have not changed. Therefore, unchanged items are not unnecessarily recreated.
# MAGIC 
# MAGIC Let's now witness how Terraform treats changes to existing resources. Let's update *cluster.tf*, changing only the value for *autotermination_minutes*.

# COMMAND ----------

dbutils.fs.put(
    "/terraform/cluster.tf",
    """
    resource "databricks_cluster" "mycluster" {
        num_workers = 1
        cluster_name = "mycluster_tfos"
        idempotency_token = "mycluster_tfos"
        spark_version = "11.1.x-scala2.12"
        node_type_id = "i3.xlarge"
        autotermination_minutes = 30
        data_security_mode = "USER_ISOLATION"
    }
    """,
    True)

# COMMAND ----------

# MAGIC %md
# MAGIC Let's view Terraform's plan to see the impact this change will have.

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform plan

# COMMAND ----------

# MAGIC %md
# MAGIC In this instance, we see that no resources are being destroyed or created. Rather, the affected resource will be modified in place.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Cleanup
# MAGIC 
# MAGIC Run the following cells to remove the resources we created throughout this section of the lab. First, let's use Terraform to destroy the configuration we created.

# COMMAND ----------

# MAGIC %sh terraform -chdir=/dbfs/terraform apply -destroy -auto-approve

# COMMAND ----------

# MAGIC %md
# MAGIC With that, we can verify in the user interface that the schema and cluster have been removed.
# MAGIC 
# MAGIC Now let's remove the */terraform* folder in DBFS and remove the widgets.

# COMMAND ----------

dbutils.widgets.removeAll()
dbutils.fs.rm("/terraform", True)

# COMMAND ----------

# MAGIC %md
# MAGIC Note that the artifacts we created in the */tmp* folder of the cluster (that is, downloaded archive and Terraform state) remain, though these will be forgotten when the cluster is terminated. For a long-running cluster, we might consider explicitly removing them but for this exercise we will not bother.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Terraform Cloud
# MAGIC 
# MAGIC With a better understanding of all that goes into managing Terraform and its associated configurations, let's now see how this fits in with the managed version of Terraform, which is freely accessible in a limited capacity. For more information on free versus paid plans, refer to <a href="https://www.terraform.io/cloud-docs/overview" target="_blank">this page</a>.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Setup
# MAGIC 
# MAGIC Before we begin we need to perform some setup. If you wish to follow along, create a Terraform account of your own and follow the instructions to log in. From there, we will see that there are a number of workflow options, but we'll follow a common one here with the following high-level steps:
# MAGIC 1. Choose the **Start from Scratch** workflow to get started. This will prompt us for an organization name, which is simply a space in which to collaborate with others in Terraform Cloud.
# MAGIC 1. Select the **Version control workflow**. In this workflow, your Terraform configuration will be driven by an upstream git repository. In this exercise, we will push configuration files that we developed in the previous section with Open Source Terraform.
# MAGIC 1. Choose a version control provider. In this example, we'll choose **GitHub > GitHub.com**.
# MAGIC 1. From here, we'll need a GitHub account and repository to host the Terraform configuration.
# MAGIC     * If you don't have a GitHub account, create that now.
# MAGIC     * Create a new repository (include a README so that the repository will be initialized). For this exercise the visiblity is unimportant.
# MAGIC 1. Let's authorize Terraform Cloud to connect with our GitHub account.
# MAGIC 1. Select the repository you just created, which will trigger the creation of a correspondingly named *workspace* - that is, a representation of the configuration that we will store in the GitHub repository. There are a number of options that can be configured, but for now let's accept the default settings and create the workspace.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Configuring authentication
# MAGIC 
# MAGIC Just like we did for open source Terraform, we must configure Terraform Cloud to be able to authenticate with Databricks. Here, we configure authentication using environment variables. This isn't the only way to accomplish this, but it's a fairly secure approach.
# MAGIC 
# MAGIC We define variables in the workspace overview page. Variables can be shared across workspaces by defining them as *variable sets* or they can be defined within a workspace.  In order to limit the scope of this sensitive information, let's go with the latter and define them at the workspace level. Let's add two environment variables, flagging both as sensitive:
# MAGIC * *DATABRICKS_HOST:* set the value to the URL of the workspace with the path component removed
# MAGIC * *DATABRICKS_TOKEN:* set the value to the token you created in the previous section. If you lost the token, then revisit the <a href="#setting/account" target="_blank">User Settings</a> page and create a new one as you did in the previous section.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Configuring the provider
# MAGIC 
# MAGIC In the GitHub repository backing the workspace, create a new filed named *versions.tf* that contains information for Terraform to be able to identify and locate the Databricks *provider*. This file is similar in function to the *terraform.tf* file we created in the previous section, though in this case we do not need to configure a backend since that is managed by Terraform Cloud.
# MAGIC 
# MAGIC Paste the following text into *versions.tf* and commit the file:
# MAGIC 
# MAGIC     terraform {
# MAGIC         required_providers {
# MAGIC             databricks = {
# MAGIC                 source  = "databricks/databricks"
# MAGIC                 version = "1.0.1"
# MAGIC             }
# MAGIC         }
# MAGIC     }

# COMMAND ----------

# MAGIC %md
# MAGIC If you followed the previous section, you may also notice that we're not going to create a corresponding *databricks.tf* file in this section. The sole purpose of this file in the previous section related to setting up the authentication credentials, which we are now handling with environment variables; so this file is no longer necessary.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Declaring a new schema
# MAGIC 
# MAGIC As we did in the previous section, let's declare a new schema in the *main* catalog named *myschema_tfc*.
# MAGIC 
# MAGIC In the GitHub repository, create a new file named *schema.tf* containing the following text, and commit the file:
# MAGIC 
# MAGIC     resource "databricks_schema" "myschema" {
# MAGIC         catalog_name = "main"
# MAGIC         name         = "myschema_tfc"
# MAGIC         comment      = "This schema is managed by Terraform Cloud"
# MAGIC     }

# COMMAND ----------

# MAGIC %md
# MAGIC ####Examining the plan
# MAGIC In the workspace overview page, select **Actions > Start new run**, leaving *Plan and apply* selected for the run type. Providing you worked through the previous section, what we see displayed in the user interface will seem familiar: Terraform displays the schema it will create.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Applying the plan
# MAGIC Still in the **Runs** page from the previous step, click **Confirm & Apply**. Specify a comment and clik **Confirm Plan**. Once this completes, open the **Data** page to validate the creation of the schema.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Declaring a compute resource
# MAGIC 
# MAGIC Now let's add a cluster to our desired configuration. Create and commit a new file named *cluster.tf* in the GitHub repository, with the following contents:
# MAGIC 
# MAGIC     resource "databricks_cluster" "mycluster" {
# MAGIC         num_workers = 1
# MAGIC         cluster_name = "mycluster_tfc"
# MAGIC         idempotency_token = "mycluster_tfc"
# MAGIC         spark_version = "11.1.x-scala2.12"
# MAGIC         node_type_id = "i3.xlarge"
# MAGIC         autotermination_minutes = 120
# MAGIC         data_security_mode = "USER_ISOLATION"
# MAGIC     }

# COMMAND ----------

# MAGIC %md
# MAGIC ####Examining the plan
# MAGIC Notice that committing the new file triggers a new run automatically. While this behavior can be handy, you can also override it or control it with branching strategies, depending on your organization's CI/CD processes.
# MAGIC 
# MAGIC In the **Runs** page, select the newly triggered run. Once again, we see that Terraform plans to create the cluster, but has no plans to do anything with the schema since nothing has changed with it since the last apply.

# COMMAND ----------

# MAGIC %md
# MAGIC ####Applying the plan
# MAGIC As before, Terraform will not apply the plan until you explicitly confirm (a behavior that can also be changed). Let's confirm as we did in the previous step. As we saw before, this is a synchronous operation that waits for the cluster to be created, so it will take some time to complete. Let's wait for that to happen before proceeding.

# COMMAND ----------

# MAGIC %md
# MAGIC #### Making changes
# MAGIC 
# MAGIC Now let's make a minor change to the cluster. In the GitHub repository, edit *cluster.tf*. Change the value for *autotermination_minutes* to *30* and commit the change. Again, a new run will be automatically triggered in response to the commit. Reviewing the changes, we see that Terraform will simply modify the cluster in place.
# MAGIC 
# MAGIC In this case we don't need to confirm; we can simply click **Discard Run**.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Cleanup
# MAGIC 
# MAGIC As everything is managed in Terraform Cloud, the only thing we need to do is destroy the resources it created. To do this, select **Settings > Destruction and Deletion** from the workspace overview page. Click **Queue destroy plan**, where you will be prompted to confirm.
# MAGIC 
# MAGIC Optionally, you can also delete the workspace by clicking **Delete from Terraform Cloud**.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC 
# MAGIC In this lab, we were introduced to Terraform constructs and operation. We learned how to apply these concepts to both the self-managed open source version of Terraform, as well as the Terraform Cloud managed service. As intricate as this lab may have seemed, it only touched on basic configurations and workflows. There are many more options available, too numerous to address in the context of a simple lab. To learn more, please refer to the following resources:
# MAGIC * The <a href="https://docs.databricks.com/dev-tools/terraform/index.html" target="_blank">Databricks Terraform provider</a> page in the Databricks documentation
# MAGIC * The <a href="https://registry.terraform.io/providers/databricks/databricks/latest/docs" target="_blank">Databricks Provider</a> page in the Terraform registry
# MAGIC * The <a href="https://www.terraform.io/docs" target="_blank">Terraform documentation</a>
# MAGIC * The online collection of Terraform tutorials, <a href="https://learn.hashicorp.com/terraform" target="_blank">HashiCorp Learn</a>

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# MAGIC <br/>
# MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>