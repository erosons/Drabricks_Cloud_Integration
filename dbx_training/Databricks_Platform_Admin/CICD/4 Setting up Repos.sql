-- Databricks notebook source
-- MAGIC %md-sandbox
-- MAGIC 
-- MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
-- MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
-- MAGIC </div>

-- COMMAND ----------

-- MAGIC %md
-- MAGIC # Setting up Repos
-- MAGIC 
-- MAGIC In this lab, you will learn how to:
-- MAGIC * Connect a workspace to a git service provider
-- MAGIC * Set up and share revision controlled notebooks in the workspace using Databricks Repos

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Overview
-- MAGIC 
-- MAGIC Databricks Repos, an extension of the Databricks Data Science and Engineering Workspace, supports code development best practices through its integration with Git repositories, while maintaining the patterns associated with standard Workspace development practices. Interacting with content in a Repo is much like interacting with the conventional folders and assets in your Workspace. Any changes you make within a Repo, however, are tracked and can be synchronized with a remote repository.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Prerequisites
-- MAGIC 
-- MAGIC If you would like to follow along with this lab, you will need workspace admin capabilities.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## First time setup
-- MAGIC 
-- MAGIC Prior to creating your first repo, there are some setup steps required to connect Databricks to your git provider (in this case, GitHub). We'll go over these steps in this section.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Obtaining GitHub credentials
-- MAGIC 
-- MAGIC In order to connect the workspace to your GitHub account, you need credentials, that is your username and a personal access token. Let's obtain that now.
-- MAGIC 
-- MAGIC 1. In the <a href="https://www.github.com" target="_blank">GitHub dashboard</a>, click on the avatar dropdown at the top-right corner of the page.
-- MAGIC 1. Select **Settings**.
-- MAGIC 1. Select **Developer settings** at the bottom of the menu.
-- MAGIC 1. Select **Personal access tokens**.
-- MAGIC 1. Click **Generate new token**.
-- MAGIC 1. Specify a **Note** and **Expiration**, and select **repo** for the scope. When selecting an expiration, be aware that longer lasting tokens might be more convenient because you don't have to roll them over and update as often, but they increase your exposure to risk if the token accidentally leaks into the wrong hands.
-- MAGIC 1. Click **Generate token**.
-- MAGIC 1. Copy the generated token somewhere safe since it will not be displayed again. Depending on how your organization is set up, you may additionally have to authorize the newly created token with your organization's SSO by following the prompts.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Connecting the workspace
-- MAGIC 
-- MAGIC With GitHub credentials set up, let's configure the workspace to use them to access repositories from your GitHub account.
-- MAGIC 
-- MAGIC 1. In the Data Science and Engineering Workspace, let’s go to the **User Settings** page, accessible from the Settings icon in the sidebar.
-- MAGIC 1. From there, let’s go to the **Git Integration** tab.
-- MAGIC 1. Now, let’s specify *GitHub* for the **Git provider**, fill in our GitHub username, and paste the token.
-- MAGIC 1. Click **Save**.
-- MAGIC 
-- MAGIC We have now integrated Databricks with our Github account! Just make sure to securely destroy your temporary copy of the token since it's securely stored in Databricks now.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Creating a Repo
-- MAGIC 
-- MAGIC With appropriate setup performed, we're now ready to create a Repo. But before we do, let's create a backing repository in GitHub, ideally one to which we have read-write access. Here I am creating and initializing a new one for the purpose of this training exercise, then copying the URL that we will need in a moment.
-- MAGIC 
-- MAGIC Note that you can create a Repo and specify the backing repository later if you really want to; that's just not the workflow we're showing here.
-- MAGIC 
-- MAGIC Now let's create that Repo.
-- MAGIC 
-- MAGIC 1. In the **Repos** page, let’s click **Add Repo**.
-- MAGIC 1. Let's specify the repository URL, which we can obtain from the git service provider. Notice that when we add the URL, the other two fields will automatically populate.
-- MAGIC 1. Let’s finalize the creation by clicking **Create**.
-- MAGIC 
-- MAGIC The Repo will be created and the underlying git repository will be cloned into the Repo; that is, your new Repo will contain a local copy of the upstream repository. We can now navigate the Repo and start developing. From here, anyone with permission can begin creating branches and modifying resources.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Sharing Repos
-- MAGIC 
-- MAGIC You may wish to have multiple users interacting with a shared copy of the Repo, rather than requiring each user to work in their own copy. 
-- MAGIC 
-- MAGIC In granting access to Repos, keep in mind that permissions apply to the entire Repo; you cannot control access at the folder or file level within a repo. The allowed permissions are:
-- MAGIC 
-- MAGIC Permission | Description
-- MAGIC --- | ---
-- MAGIC **Can Read** | read-only access to Repo contents
-- MAGIC **Can Run** | **Can Read** plus ability to run notebooks in the Repo
-- MAGIC **Can Edit** | **Can Run** plus the ability modify the files within the Repo (but no file or repo management capabilities)
-- MAGIC **Can Manage** | complete administrative capabilities over the Repo
-- MAGIC 
-- MAGIC Note that **Can Edit** only allows you modify the file that are present in the Repo. You can't add, remove, move or rename files. You also can't manage the Repo itself, meaning that you cannot view changes, create branches, commit, push, or pull.
-- MAGIC 
-- MAGIC There are a couple approaches to sharing Repos, which we will discuss now.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Providing direct access to a Repo
-- MAGIC 
-- MAGIC In this simple model, we provide access to a Repo that we have already set up. This approach is typical when you have "checked out" a Repo in your personal folder that you then want to collaborate on. Let's apply this model to share the Repo we set up earlier with all workspace users, enabling them with read-only access to the Repo.
-- MAGIC 
-- MAGIC 1. In the **Repos** page, located the desired Repo.
-- MAGIC 1. Click the chevron to the right of your menu item and select **Permissions**.
-- MAGIC 1. Open the dropdown menu in the **NAME** column. Select the *all users* entry in the **Groups** section
-- MAGIC 1. In the **PERMISSION** column, select *Can Read*.
-- MAGIC 1. Click **Add**, then **Save**.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Sharing Repos using folders
-- MAGIC 
-- MAGIC In this model, we use folders to contain and share Repos. In this context, folders adopt the Repo permission model, rather than the permission model for standard folders in the workspace, and any contained Repos automatically inherit the permissions set on the containing folder.
-- MAGIC 
-- MAGIC While this approach is an elegant long-term solution, it requires a bit more thought over how to organize your folders and the permissions, and it also must be done by a workspace admin. A typical usage is to create folders representing the various development stages (*Dev*, *Staging*, *Prod*), each containing Repos for the appropriate branches. Though *Prod* would most certainly be read-only for all non-admin users, you might consider more permissive access for *Staging* and *Dev*.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC #### Creating top-level folders
-- MAGIC 
-- MAGIC Let's create two top-level folders, *Dev* and *Prod* for the purpose of sharing Repos.
-- MAGIC 
-- MAGIC 1. In the **Repos** page, let’s select **Add folder** in the leftmost column of the navigator.
-- MAGIC 1. Let's specify the name *Dev* and create the folder.
-- MAGIC 1. Now let's configure the permission for this new folder. In this case, let's allow all users to modify files within its Repos. To do this we click the chevron to the right of the folder menu item and select **Permissions**.
-- MAGIC 1. Now let's select *all users*  and *Can Edit*, then save our changes.
-- MAGIC 
-- MAGIC Let's repeat the process, this time creating a folder named *Prod* that conveys *Can Read* permissions to all users.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC #### Creating a Development Repo
-- MAGIC 
-- MAGIC With top-level folders created, populating them follows a very similar workflow to what we've seen.
-- MAGIC 
-- MAGIC 1. In the **Repos** page, let’s select the *dev* folder in the leftmost column of the navigator.
-- MAGIC 1. Click **Add Repo**, and from there we follow the same procedure as we did in the earlier section, *Creating a Repo*.
-- MAGIC 
-- MAGIC Because users will be allowed to make changes to the files in this Repo, we should follow administrative best practices by setting up a development branch to mitigate the chance of accidentally pushing such changes to *main*. Let's do this now.
-- MAGIC 
-- MAGIC 1. Let's open the Repos dialog for the *dev* Repo.
-- MAGIC 1. Let’s click **Create Branch** and specify the name for the branch we want to create.
-- MAGIC 
-- MAGIC Since creating a new branch automatically selects it as the current working branch, no further steps are necessary. Any changes pushed to the upstream repository will be against this branch. From there, changes can be merged over to other branches (or *main*) as per your organization's development processes.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC #### Creating a Production Repo
-- MAGIC 
-- MAGIC Now let's set up a Repo for the *prod* folder, following the same procedure we did for the *dev* folder.
-- MAGIC 
-- MAGIC You can create a branch for this folder if you like, but this represents a bit of a trade-off. If you do this, any changes (for example, by an admin) are guaranteed to never be pushed to *main*. On the flip side, keeping this Repo locked on *main* makes it easy to track and view the most recent changes.

-- COMMAND ----------

-- MAGIC %md-sandbox
-- MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
-- MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
-- MAGIC <br/>
-- MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>