# Databricks notebook source
# MAGIC %md-sandbox
# MAGIC 
# MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC # Implementing security best practices in your notebooks
# MAGIC 
# MAGIC In this lab you will learn how to:
# MAGIC * Apply parametrization to improve the security and maintainability of your notebooks
# MAGIC * Set up and use Databricks secrets to secure sensitive information

# COMMAND ----------

# MAGIC %md
# MAGIC ##Prerequisites
# MAGIC 
# MAGIC If you would like to follow along with this lab, you will need access to an organization in GitHub, with the ability to create an API token.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Overview
# MAGIC 
# MAGIC We often need to write notebooks that interact with services that require credentials. We don't want sensitive information like passwords or tokens to fall into the wrong hands. As easy as it is to embed such credentials into the code of your notebook, doing so is a very bad idea from a security standpoint, because you can easily leak credentials if you share the notebook with someone else, or place it under revision control where it's visible to anyone with access to the repository.
# MAGIC 
# MAGIC Parametrizing credentials is a better idea, but we need an approach that is secure, and that works equally well when running the notebook interactively versus as a scheduled job. This is where Databricks secrets fits in. Databricks secrets abstracts the complexity of hiding sensitive information, and makes it accessible through the CLI, APIs, or through Databricks utilities.
# MAGIC 
# MAGIC In this lab, we'll encounter a fairly typical authentication challenge and work through these two approaches to overcome it.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Implementing a simple GitHub application
# MAGIC 
# MAGIC Let's examine the beginnings of an application that uses the GitHub REST API to query some repository metrics. Before proceeding, edit the following cell:
# MAGIC * Replace *ORG* with your GitHub organization name
# MAGIC * Replace *TOKEN* with a personal access token. Obtain one by following these high-level steps:
# MAGIC     1. In the <a href="https://www.github.com" target="_blank">GitHub dashboard</a>, click on the avatar dropdown at the top-right corner of the page.
# MAGIC     1. Select **Settings**.
# MAGIC     1. Select **Developer settings** at the bottom of the menu.
# MAGIC     1. Select **Personal access tokens**.
# MAGIC     1. Click **Generate new token**.
# MAGIC     1. Specify a **Note** and **Expiration**, and select **repo** for the scope.
# MAGIC     1. Click **Generate token**.
# MAGIC     1. Copy the generated token. Depending on how your organization is set up, you may additionally have to authorize the token by clicking **Configure SSO** and following the prompts.
# MAGIC     
# MAGIC Once you've made these two substitutions, run the cell.

# COMMAND ----------

DBACADEMY_GITHUB_ORG = "ORG"
DBACADEMY_GITHUB_TOKEN = "TOKEN"

# COMMAND ----------

# MAGIC %md
# MAGIC Using a combination of Python *requests* and PySpark, let's query repositories using the organization name and token for authorization, and store some results in a DataFrame.

# COMMAND ----------

import requests

# Request a list of repository organizations as per https://docs.github.com/en/rest/repos/repos#list-organization-repositories
r = requests.get(f"https://api.github.com/orgs/{DBACADEMY_GITHUB_ORG}/repos",
                 params = { "per_page": 100 },
                 headers = { "Authorization": f"Bearer {DBACADEMY_GITHUB_TOKEN}" }
                )

# Read the JSON output into a DataFrame with select columns. No error checking in this simple example. If the above request failed,
# the following statement will fail.
df = spark.read.json(sc.parallelize([ r.text ])).select("name","git_url","created_at","open_issues_count","visibility","watchers_count")
display(df)

# COMMAND ----------

# MAGIC %md
# MAGIC As we can see, this works, however it should be apparent that the above pattern is terrible practice, for two reasons:
# MAGIC * Two sensitive pieces of information (your token, and less cricitally, your organization's name) are exposed in clear text within the notebook. Anyone with whom this notebook is shared, either deliberately or inadvertently, will be able to access the service using your credentials.
# MAGIC * It also introduces maintenance challenges if you have multiple notebooks using the same credentials. When credentials are updated (in this case, when the token is rolled over), each notebook would have to be manually updated.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Solving the problem with parametrization
# MAGIC 
# MAGIC Parametrizing the sensitive elements is a more secure and scalable option. To demonstrate this, let's run the following cell.

# COMMAND ----------

dbutils.widgets.text(name='github_org', defaultValue='')
dbutils.widgets.text(name='github_token', defaultValue='')

# COMMAND ----------

# MAGIC %md
# MAGIC Now, referring back to the cell you modified earlier, copy the following values into the fields above:
# MAGIC * Copy the value for *DBACADEMY_GITHUB_ORG* into the *github_org* field
# MAGIC * Copy the value for *DBACADEMY_GITHUB_TOKEN* into the *github_token* field
# MAGIC 
# MAGIC The cell below is a rephrasing of the code we saw earlier, adjusted to use the field values rather than the hardcoded variables. Modifying the values in the fields will automatically trigger the execution of the cell, which will succeed if the organization and token are both valid.

# COMMAND ----------

import requests

# Request a list of repository organizations as per https://docs.github.com/en/rest/repos/repos#list-organization-repositories
r = requests.get(f"https://api.github.com/orgs/{dbutils.widgets.get('github_org')}/repos",
                 params = { "per_page": 100 },
                 headers = { "Authorization": f"Bearer {dbutils.widgets.get('github_token')}" }
                )

# Read the JSON output into a DataFrame with select columns. No error checking in this simple example. If the above request failed,
# the following statement will fail.
df = spark.read.json(sc.parallelize([ r.text ])).select("name","git_url","created_at","open_issues_count","visibility","watchers_count")
display(df)

# COMMAND ----------

# MAGIC %md
# MAGIC The values are now parametrized. They are no longer hardcoded which in itself is a massive improvement from a security standpoint. This change also improves usability, because now the values can be dynamically specified in one of three ways:
# MAGIC * When running the notebook interactively as we are doing here, values can be specified by filling in the fields
# MAGIC * When running the notebook from another notebook, values can be specified as part of the invocation
# MAGIC * When running the notebook from a job, values can be specified in the **Parameters** section of the job configuration
# MAGIC 
# MAGIC While this is definitely more secure, let's look at one final option that presents the most secure option: Databricks secrets.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Solving the problem with Databricks secrets
# MAGIC 
# MAGIC Databricks secrets provides a mechanism to securely store sensitive information in a way that it can be made available across the workspace. Notebooks can then pull in the information they need directly using the **`secrets`** command provided by **dbutils**.
# MAGIC 
# MAGIC Secrets provides some important security benefits over simple parametrization:
# MAGIC * Secrets are scoped, allowing you to categorize sensitive information into distinct namespaces
# MAGIC * Secrets can be access controlled, allowing you to restrict which users have access to which secrets
# MAGIC 
# MAGIC As we'll see, there's slightly more setup effort involved, however we'll also see that using secrets in your notebooks is no more difficult than parameters.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Setup
# MAGIC 
# MAGIC At a mininum, setting up secrets involves defining a scope, then adding secrets to the scope. Both of these tasks can only be done using the Databricks CLI or the secrets API. For this lab, we'll use the API. Full information on the API can be found <a href="https://docs.databricks.com/dev-tools/api/latest/secrets.html" target="_blank">here</a>.

# COMMAND ----------

# MAGIC %md
# MAGIC ####Setting up API credentials
# MAGIC 
# MAGIC If you followed the lab *Using Databricks APIs*, you'll recall that we need a base URL for the APIs and a token for API authentication before we can proceed. Run the following cell to create a landing zone for the needed inputs, then follow the instructions below.

# COMMAND ----------

dbutils.widgets.text(name='url', defaultValue='')
dbutils.widgets.text(name='token', defaultValue='')

from urllib.parse import urlparse,urlunsplit

u = urlparse(dbutils.widgets.get('url'))

import os

os.environ["DBACADEMY_API_TOKEN"] = f"Authorization: Bearer {dbutils.widgets.get('token')}"
os.environ["DBACADEMY_API_URL"] = urlunsplit((u.scheme, u.netloc, f"/api/2.0", "", ""))

os.environ["DBACADEMY_GITHUB_ORG"] = dbutils.widgets.get('github_org')
os.environ["DBACADEMY_GITHUB_TOKEN"] = dbutils.widgets.get('github_token')

# COMMAND ----------

# MAGIC %md
# MAGIC Now let's populate the two fields as follows.
# MAGIC 1. Go to <a href="#setting/account" target="_blank">User Settings</a> (which is also accessible from the left sidebar by selecting **Settings > User Settings**).
# MAGIC 1. Select the **Access tokens** tab.
# MAGIC 1. Click **Generate new token**.
# MAGIC     1. Specify a **Comment** such as *Security lab*. Choose a short value for **Lifetime**; for the purpose of this lab, one or two days is sufficient.
# MAGIC     1. Click **Generate**.
# MAGIC     1. Copy the resulting token to the *token* field.
# MAGIC     1. Click **Done**.
# MAGIC 1. Copy the URL of your workspace (the contents of the address bar in your current browser session is sufficient) into the *url* field.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Creating a secret scope
# MAGIC 
# MAGIC Now that we have API access, let's invoke the API for creating a new secret scope.
# MAGIC 
# MAGIC If we were using the CLI, an equivalent command for this would be **`databricks secrets create-scope --scope mysecrets_cli`**.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/scopes/create" -d @- | json_pp
# MAGIC {
# MAGIC   "scope": "mysecrets_api"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC #### Listing scopes
# MAGIC Let's validate the scope creation by invoking the API to list scopes. The equivalent CLI command for this would be **`databricks secrets list-scopes`**.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/scopes/list" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC ### Adding secrets
# MAGIC With a scope prepared, let's add two secrets containing the GitHub organization and token. In this case we will take advantage of the fact that we have widgets already populated with these values.
# MAGIC 
# MAGIC If we were using the CLI, the equivalent command for this would be **`databricks secrets put --scope mysecrets_cli --key github_org`**. This would require an interactive shell, as it will open an editor application for you to fill in the value.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/put" -d @- | json_pp
# MAGIC {
# MAGIC   "scope": "mysecrets_api",
# MAGIC   "key": "github_org",
# MAGIC   "string_value": "${DBACADEMY_GITHUB_ORG}"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/put" -d @- | json_pp
# MAGIC {
# MAGIC   "scope": "mysecrets_api",
# MAGIC   "key": "github_token",
# MAGIC   "string_value": "${DBACADEMY_GITHUB_TOKEN}"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC #### Listing secrets
# MAGIC Let's validate the secrets creation by invoking the API to list secrets. The equivalent CLI command for this is **`databricks secrets list mysecrets_cli`**.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/list?scope=mysecrets_api" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC ### Using secrets
# MAGIC With our sensitive values now stored as secrets, let's update the original application to use these secrets instead. As compared to the parametrization example, the changes are minimal. Here's what needed to happen:
# MAGIC * Replace **`dbutils.widgets.get()`** calls with **`dbutils.secrets.get()`**
# MAGIC * To those calls, add the scope name as the first parameter
# MAGIC * Ensure that the second parameter matches to the *key* value of the secret

# COMMAND ----------

import requests
dbutils.secrets.get
# Request a list of repository organizations as per https://docs.github.com/en/rest/repos/repos#list-organization-repositories
r = requests.get(f"https://api.github.com/orgs/{dbutils.secrets.get('mysecrets_api', 'github_org')}/repos",
                 params = { "per_page": 100 },
                 headers = { "Authorization": f"Bearer {dbutils.secrets.get('mysecrets_api', 'github_token')}" }
                )

# Read the JSON output into a DataFrame with select columns. No error checking in this simple example. If the above request failed,
# the following statement will fail.
df = spark.read.json(sc.parallelize([ r.text ])).select("name","git_url","created_at","open_issues_count","visibility","watchers_count")
display(df)

# COMMAND ----------

# MAGIC %md
# MAGIC That seems simple enough, but is it really secure? Let's try to access the contents of one of the secrets directly.

# COMMAND ----------

print(dbutils.secrets.get('mysecrets_api', 'github_token'))

# COMMAND ----------

# MAGIC %md
# MAGIC We see that the output is redacted, improving security by eliminating the chance of the real secret value accidently being included in cell output.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Access control
# MAGIC If you followed along with the *Securing the Workspace* lab, we went over how to use access control to secure assets within the workspace. Access control extends to secrets and is managed at the scope level. Like the secrets and scopes themselves, access control lists (ACLs) for secrets must be manipulated using the CLI or API.
# MAGIC 
# MAGIC Let's see that in action now.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Granting access to secrets
# MAGIC 
# MAGIC Let's grant **`READ`** access to everyone in the workspace (denoted by the special workspace local group named *users*) on the secret scope we created earlier, by invoking the API for creating a new ACL.
# MAGIC 
# MAGIC If we were using the CLI, an equivalent command for this would be **`databricks secrets put-acl --scope mysecrets_cli --principal users --permission READ`**.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/acls/put" -d @- | json_pp
# MAGIC {
# MAGIC   "scope": "mysecrets_api",
# MAGIC   "principal": "users",
# MAGIC   "permission": "READ"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC #### Listing grants
# MAGIC Let's validate the ACL creation by invoking the API to list secret ACLs. The equivalent CLI command for this is **`databricks secrets list-acls mysecrets_cli`**.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/acls/list?scope=mysecrets_api" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC Here we see the **`READ`** grant we just issued, as well as the default grant allowing the creator to **`MANAGE`** the scope.

# COMMAND ----------

# MAGIC %md
# MAGIC ###Revoking grants
# MAGIC The ability to revoke previously issued grants is important; let's see how to do that now.
# MAGIC 
# MAGIC If we were using the CLI, an equivalent command for this would be **`databricks secrets delete-acl --scope mysecrets_cli --principal users`**.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/acls/delete" -d @- | json_pp
# MAGIC {
# MAGIC   "scope": "mysecrets_api",
# MAGIC   "principal": "users"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md
# MAGIC Let's list the ACLs once again to validate the removal.

# COMMAND ----------

# MAGIC %sh curl -s -X GET -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/acls/list?scope=mysecrets_api" | json_pp

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleanup
# MAGIC 
# MAGIC Run the following cell to delete the scope we created, which will remove the contained secrets and any associated ACLs. If using the CLI, the equivalent command would be **`databricks secrets delete-scope --scope mysecrets_cli`**.

# COMMAND ----------

# MAGIC %sh cat << EOF | curl -s -X POST -H "${DBACADEMY_API_TOKEN}" "${DBACADEMY_API_URL}/secrets/scopes/delete" -d @- | json_pp
# MAGIC {
# MAGIC   "scope": "mysecrets_api"
# MAGIC }
# MAGIC EOF

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# MAGIC <br/>
# MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>