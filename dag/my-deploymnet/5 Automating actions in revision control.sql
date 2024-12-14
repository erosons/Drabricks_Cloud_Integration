-- Databricks notebook source
-- MAGIC %md-sandbox
-- MAGIC 
-- MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
-- MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
-- MAGIC </div>

-- COMMAND ----------

-- MAGIC %md
-- MAGIC # Automating actions in revision control
-- MAGIC 
-- MAGIC In this lab, you will learn how to:
-- MAGIC * Automatically perform Databricks actions in response to code updates in revision control

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Overview
-- MAGIC 
-- MAGIC Databricks Repos, an extension of the Databricks Data Science and Engineering Workspace, supports code development best practices through its integration with Git repositories. However, in order to automate a complete CI/CD loop, there needs to be a way to trigger Databricks actions in response to code revision control events. As an example, you may want to run automated tests when someone pushes a change to a development branch, or you may want to schedule data engineering, analytics, and machine learning workloads in response to changes in the production branch.
-- MAGIC 
-- MAGIC In this lab, we explore the application of GitHub Actions, a mechanism that enables you to define responses that are triggered by various repository events.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Prerequisites
-- MAGIC 
-- MAGIC This lab follows on to the work that was done in the *Setting Up Repos* lab; therefore you need to complete that lab first. Specifically, you will need:
-- MAGIC * A GitHub repository with read-write access
-- MAGIC * A *Prod* folder containing a Databricks Repo connected to the GitHub repository
-- MAGIC 
-- MAGIC Though nothing in this lab inherently requires workspace admin capabilities, the way the repositories were set up in the aforementioned lab will require such privileges for this exercise. With appropriate identity and permission configuration, however, actions can be applied by anyone in the organization.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Creating a GitHub action
-- MAGIC 
-- MAGIC In this section we'll set up the simple framework to trigger an update on our *Prod* repo whenever changes are pushed to the upstream repository through the use of a GitHub **action**.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Overview of GitHub Actions
-- MAGIC 
-- MAGIC According to <a href="https://docs.github.com/en/actions/learn-github-actions" target="_blank">GitHub</a>, **Actions** is a feature that allows you to automate your build, test, and deployment pipeline. Using actions, you can create workflows that build and test every pull request to your repository, or deploy merged pull requests to production.
-- MAGIC 
-- MAGIC Actions actually go beyond that and allow you to define responses to pretty much any event occuring in your repository. There's a lot of flexibility as to what you can do in actions, with a vast <a href="https://github.com/marketplace?type=actions" target="_blank">marketplace</a> of existing, ready-to-use actions that you can leverage in your own.
-- MAGIC 
-- MAGIC Before we go any further, it helps to have a basic understanding of some key concepts:
-- MAGIC Concept | Definiton
-- MAGIC ---|---
-- MAGIC **Event** | A specific activity in a repository that triggers a **workflow**. Examples of events include a push, creation of a pull request, opening an issue, and many more.
-- MAGIC **Workflow** | An automated process that will run one or more **jobs**.
-- MAGIC **Job** | A set of steps in a **workflow** that execute on the same **runner**.
-- MAGIC **Runner** | A pristine VM that runs **workflows** when triggered. Each runner can run a single **job** at a time. Various environments are available including Ubuntu Linux, Microsoft Windows, and macOS. Runners can also be self hosted.
-- MAGIC 
-- MAGIC Workflows are defined by <a href="https://yaml.org/" target="_blank">YAML files</a> located in the */.github/workflows/* directory of your repository.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Setting up authentication for Databricks
-- MAGIC 
-- MAGIC Because our action will be accessing Databricks remotely, we need to set up credentials for authentication: that is, the URL of your Databricks instance and a personal access token. We'll securely store these credentials using GitHub's <a href="https://docs.github.com/en/actions/security-guides/encrypted-secrets" target="_blank">encrypted secrets</a>. 
-- MAGIC 
-- MAGIC In general, Databricks advocates using a service principal for applications like CI/CD tools, but for the purpose of this simple exercise, we'll generate a token using our own identity.
-- MAGIC 
-- MAGIC 1. Go to <a href="#setting/account" target="_blank">User Settings</a> (which is also accessible from the left sidebar by selecting **Settings > User Settings**).
-- MAGIC 1. Select the **Access tokens** tab.
-- MAGIC 1. Click **Generate new token**.
-- MAGIC     1. Specify a **Comment** such as *GitHub Test*. Choose a short value for **Lifetime**; for the purpose of this lab, one or two days is sufficient.
-- MAGIC     1. Click **Generate**.
-- MAGIC     1. Copy the resulting token to the clipboard and click **Done**.
-- MAGIC 
-- MAGIC With a token created, let's create a GitHub secret to store it, as well as the URL of our Databricks instance.
-- MAGIC 
-- MAGIC 1. In the GitHub repository page, select **Settings**.
-- MAGIC 1. Select **Secrets > Actions**.
-- MAGIC 1. Let's click **New repository secret**. Let's specify *DATABRICKS_TOKEN* for the name, and paste the token as the secret, then click **Add secret**.
-- MAGIC 1. Let's repeat the step to add another secret named *DATABRICKS_HOST*, with the URL of the workspace as the secret (with the path component removed).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Creating a simple Action
-- MAGIC 
-- MAGIC Let's create a simple action. In the GitHub repository, create a new file, */.github/workflows/dbupdaterepo.yml*, and populate it with the following YAML:
-- MAGIC     
-- MAGIC     on:
-- MAGIC      push
-- MAGIC 
-- MAGIC     jobs:
-- MAGIC      update:
-- MAGIC       runs-on: ubuntu-latest
-- MAGIC 
-- MAGIC       steps:
-- MAGIC         - name: Setup Python
-- MAGIC           uses: actions/setup-python@v2
-- MAGIC           with:
-- MAGIC             python-version: 3.6
-- MAGIC 
-- MAGIC         - name: Install Databricks CLI
-- MAGIC           run: |
-- MAGIC             python -m pip install --upgrade databricks-cli
-- MAGIC 
-- MAGIC         - name: Remote update Prod Repo
-- MAGIC           env:
-- MAGIC             DATABRICKS_HOST: ${{ secrets.DATABRICKS_HOST }}
-- MAGIC             DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_TOKEN }}
-- MAGIC           run: |
-- MAGIC             databricks repos update --branch main --path /Repos/Prod/test-rw-repo
-- MAGIC     
-- MAGIC Now let's commit the file. Because we are committing straight to the upstream repository, this is like a **push** and thus the new action will be triggered!
-- MAGIC 
-- MAGIC We can verify this by going to the **Actions** page. Notice how we can examine the workflow output, which can be a useful debugging tool when things don't work as planned.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Validating the action
-- MAGIC 
-- MAGIC Let's go back to our workspace and examine the Repo in *Prod*. Notice now the presence of the *.github* folder, which in turn contains *workflows* and *dbupdaterepo.yml*. These weren't there prior to this commit; this is evidence that our Repo has been automatically updated in response to the commit we made right from within GitHub.
-- MAGIC 
-- MAGIC With this action in place the Repo will be maintained in an up-to-date state, so that you can always see the latest changes in *Prod* (subject to a latency of a half-minute or so).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Leveraging actions from the marketplace
-- MAGIC 
-- MAGIC Every organization has unique CI/CD requirements, and there's really no limit to what you can do with Databricks and GitHub actions. Here we've seen a very simple example of what you can do and how you can interact with your Databricks environment in reponse to revision control events.
-- MAGIC 
-- MAGIC To further you in your journey, two ready-to-use actions are available:
-- MAGIC 
-- MAGIC * **databricks/run-notebook** provides the framework for executing a Notebook within a GitHub action. This can be a useful tool for executing tests against committed code, validating pipeline performance, etc.
-- MAGIC * **databricks/uploade-dbfs-temp** uploads a file to DBFS for temporary usage during job execution
-- MAGIC 
-- MAGIC The code below illustrates one possible invocation of **run-notebook** however many options are possible and you're encouraged to see more by visiting their respective GitHub repositories as documented <a href="https://docs.databricks.com/dev-tools/ci-cd/ci-cd-github.html" target="_blank">here</a>.
-- MAGIC 
-- MAGIC         steps:
-- MAGIC           …
-- MAGIC           - name: Run notebook
-- MAGIC             uses: databricks/run-notebook@v0
-- MAGIC             with:
-- MAGIC               databricks-host: ${{ secrets.DATABRICKS_HOST }}
-- MAGIC               databricks-token: ${{ secrets.DATABRICKS_TOKEN }}
-- MAGIC               workspace-notebook-path: /Users/…
-- MAGIC               new-cluster-json: >
-- MAGIC                 {
-- MAGIC                   "num_workers": 1,
-- MAGIC                   "spark_version": "11.1.x-scala2.12",
-- MAGIC                   "node_type_id": "i3.xlarge"
-- MAGIC                 }
-- MAGIC               # Allow all users to view notebook results
-- MAGIC               access-control-list-json: >
-- MAGIC                 [
-- MAGIC                   {
-- MAGIC                     "group_name": "users",
-- MAGIC                     "permission_level": "CAN_VIEW"
-- MAGIC                   }
-- MAGIC                 ]
-- MAGIC 
-- MAGIC These actions, and many more, are available in the <a href="https://github.com/marketplace?type=actions" target="_blank">marketplace</a> so feel free to check it out.

-- COMMAND ----------

-- MAGIC %md-sandbox
-- MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
-- MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
-- MAGIC <br/>
-- MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>