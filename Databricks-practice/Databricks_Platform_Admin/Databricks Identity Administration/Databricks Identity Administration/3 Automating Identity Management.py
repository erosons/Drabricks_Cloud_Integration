# Databricks notebook source
# MAGIC %md-sandbox
# MAGIC 
# MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC # Automating identity management
# MAGIC 
# MAGIC In this lab you will learn how to:
# MAGIC * Remotely administer account level users and groups using the SCIM API

# COMMAND ----------

# MAGIC %md
# MAGIC ##Prerequisites
# MAGIC 
# MAGIC If you would like to follow along with this lab, you will need account administrator capabilities over your Databricks account.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Overview
# MAGIC 
# MAGIC Databricks exposes all its major functionality as a collection of REST APIs. In this lab, we will focus on using the SCIM API to remotely create and delete users, service principals and groups.
# MAGIC 
# MAGIC There are a number of ways to apply usage of this API:
# MAGIC 
# MAGIC * Implement code that uses a low level web access API (like Python's **requests** module for example) to issue REST calls and interpret the results
# MAGIC * Use a client that provides low level web access (like **curl**, **wget** or **Postman**) to issue calls and view the results
# MAGIC * Integrate a higher level automation framework that supports SCIM. SCIM is an open standard implemented by many identity provider frameworks. For general info on SCIM, refer to the <a href="http://www.simplecloud.info/" target="_blank">SCIM website</a>.
# MAGIC 
# MAGIC Regardless of which approach you take to hook into your Databricks account using SCIM, you need the following:
# MAGIC * The URL of the Databricks SCIM interface. This is the top-level URL on which all API endpoints are based.
# MAGIC * A SCIM token for authenticating with the server.
# MAGIC 
# MAGIC Depending on the operation, you may need to specify additional data to fulfill the request.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup
# MAGIC 
# MAGIC In order to invoke the Databricks account SCIM API, we need:
# MAGIC * To enable user provisioning
# MAGIC * The SCIM API URL, which includes your Databricks account URL and account ID
# MAGIC * A SCIM token
# MAGIC 
# MAGIC Run the following cell to create a landing zone for the needed inputs, then follow the instructions below.

# COMMAND ----------

dbutils.widgets.text(name='url', defaultValue='')
dbutils.widgets.text(name='token', defaultValue='')

import os
os.environ["DBACADEMY_SCIM_TOKEN"] = f"Authorization: Bearer {dbutils.widgets.get('token')}"
os.environ["DBACADEMY_SCIM_URL"] = dbutils.widgets.get('url')

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's populate the two fields as follows.
# MAGIC 
# MAGIC 1. In the account console, click **Settings** in the left sidebar.
# MAGIC 1. Select the **User provisioning** tab.
# MAGIC 1. Enable user provisioning, if it isn't already enabled.
# MAGIC 1. Click **Regenerate token**, copy the resulting token to the clipboard, click **Done** and paste the token to the *token* field.
# MAGIC 1. Copy the value for **Account SCIM URL** into the *url* field
# MAGIC 
# MAGIC Pasting these values into their associated fields will automatically trigger the previous cell, which will populate OS environment variables that will be used by the commands throughout this lab.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Users and service principals
# MAGIC 
# MAGIC In the lab *Managing Account Identities*, we saw how to manage users and service prinicpals using the account console. Let's perform a similar set of tasks using the SCIM API. For more info, refer to the <a href="https://docs.databricks.com/dev-tools/api/latest/scim/account-scim.html" target="_blank">Account SCIM API documentation</a>.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Querying users
# MAGIC Let's get a list of users in the account.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/Users" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC We can get an expanded view of a specific user. From the output above, identify a user and copy the value for *id*. Substitute that value for *ID* in the following cell and run it.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/Users/ID" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC ### Creating a user
# MAGIC Let 's add a new user to our account. For this we need to **`POST`** to the same endpoint that we queried earlier. We'll need to specify JSON data describing the new user; at a minimum, a *userName*. Using a combination of shell features, we are inlining the JSON data below the command itself.
# MAGIC 
# MAGIC For the purposes of this training exercise, I am using a temporary email address courtesy of <a href="https://www.dispostable.com/" target="_blank">dispostable.com</a>. When following along, feel free to use an email address of your choosing.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_SCIM_TOKEN}" -H "Content-type: text/json" "${DBACADEMY_SCIM_URL}/Users" -d @- | json_pp
# MAGIC {
# MAGIC   "userName": "dbanalyst0906_curl@dispostable.com"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC As we would expect when creating a user in the account console, the new user will be issued an email inviting them to join and set their password.
# MAGIC 
# MAGIC As a reminder, this operation creates an identity at the account level only. This user will not be able to access Databricks services yet since they have not been assigned to any workspaces.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Querying service principals
# MAGIC Let's get a list of service principals in the account.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/ServicePrincipals" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC We can get a view of a specific service principal. From the output above, identify a service principal and copy the value for *id* (not *applicationId*). Substitute that value for *ID* in the following cell and run it.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/ServicePrincipals/ID" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC ### Creating a service principal
# MAGIC Let 's add a new service principal to our account. For this we need to **`POST`** to the same endpoint that we queried earlier. We need to specify JSON data describing the new service principal; at a minimum, a *displayName*. To do this we'll apply the same pattern we used earlier.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_SCIM_TOKEN}" -H "Content-type: text/json" "${DBACADEMY_SCIM_URL}/ServicePrincipals" -d @- | json_pp
# MAGIC {
# MAGIC   "displayName": "service_principal_curl"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC ## Groups
# MAGIC 
# MAGIC Now that we know the basics of querying and creating users and service principals, let's turn our attention to groups.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Querying groups
# MAGIC Let's get a list of groups in the account.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/Groups" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC We can get a view of a specific group. From the output above, identify a group and copy the value for *id*. Substitute that value for *ID* in the following cell and run it.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/Groups/ID" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC ### Creating a group
# MAGIC Let 's add a new group to our account. For this we need to **`POST`** to the same endpoint that we queried earlier. We'll need to specify JSON data describing the new group; at a minimum, a *displayName*. To do this we'll apply the same pattern we used earlier.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_SCIM_TOKEN}" -H "Content-type: text/json" "${DBACADEMY_SCIM_URL}/Groups" -d @- | json_pp
# MAGIC {
# MAGIC   "displayName": "group_curl"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC This creates an empty group. The API allows you to specify members at create time, but we'll see how to do this in a separate call now.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Adding group members
# MAGIC Let's add a the user and service principal we created earlier to this new group. For this we need to **`PATCH`** the group-specific endpoint. The JSON data required to support this operation is a little more complex than the previous examples, and we'll need to perform three substitutions before executing the following cell:
# MAGIC * Replace *GROUP* with the *id* value from the group creation output
# MAGIC * Replace *USER* with the *id* value from the user creation output
# MAGIC * Replace *SERVICEPRINCIPAL* with the *id* value from the service principal creation output

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X PATCH -H "${DBACADEMY_SCIM_TOKEN}" -H "Content-type: text/json" "${DBACADEMY_SCIM_URL}/Groups/GROUP" -d @- | json_pp
# MAGIC {
# MAGIC   "Operations": [
# MAGIC     {
# MAGIC       "op": "add",
# MAGIC       "value": {
# MAGIC         "members": [
# MAGIC           {
# MAGIC             "value": "USER"
# MAGIC           },
# MAGIC           {
# MAGIC             "value": "SERVICEPRINCIPAL"
# MAGIC           }
# MAGIC         ]
# MAGIC       }
# MAGIC     }
# MAGIC   ]
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC ### Removing group members
# MAGIC Removing members from a group is done with a similar **`PATCH`** operation, but the JSON syntax is different. Let's see this in action by removing the service principal from the group. We'll need to perform two substitutions before executing the following cell:
# MAGIC * Replace *GROUP* with the *id* value from the group creation output
# MAGIC * Replace *SERVICEPRINCIPAL* with the *id* value from the service principal creation output

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X PATCH -H "${DBACADEMY_SCIM_TOKEN}" -H "Content-type: text/json" "${DBACADEMY_SCIM_URL}/Groups/GROUP" -d @- | json_pp
# MAGIC {
# MAGIC   "Operations": [
# MAGIC     {
# MAGIC       "op": "remove",
# MAGIC       "path": "members[value eq \"SERVICEPRINCIPAL\"]"
# MAGIC     }
# MAGIC   ]
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup
# MAGIC 
# MAGIC Let's now explore how to remove principals by cleaning up those that we created in this lab.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Deleting groups
# MAGIC Let's delete the group we created. For this we use **`DELETE`** against the same endpoint that we used earlier for adding and removing members. Replace *GROUP* with the *id* value from the group creation output.
# MAGIC 
# MAGIC Note that this only deletes the group but leaves its members behind. We will delete those explicitly.

# COMMAND ----------

# MAGIC %sh curl -s -X DELETE -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/Groups/GROUP" 

# COMMAND ----------

# MAGIC %md
# MAGIC ### Deleting users
# MAGIC Let's delete the user we created. Again we use **`DELETE`** against the same endpoint we'd use to query a user. Replace *USER* with the *id* value from the user creation output.

# COMMAND ----------

# MAGIC %sh curl -s -X DELETE -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/Users/USER" 

# COMMAND ----------

# MAGIC %md
# MAGIC ### Deleting service principals
# MAGIC Finally, let's delete the service principal we created. Again we use **`DELETE`** against the same endpoint we'd use to query a service principal. Replace *SERVICEPRINCIPAL* with the *id* value from the service principal creation output.

# COMMAND ----------

# MAGIC %sh curl -s -X DELETE -H "${DBACADEMY_SCIM_TOKEN}" "${DBACADEMY_SCIM_URL}/ServicePrincipals/SERVICEPRINCIPAL" 

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# MAGIC <br/>
# MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>