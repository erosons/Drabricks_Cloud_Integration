-- Databricks notebook source
-- MAGIC %md-sandbox
-- MAGIC 
-- MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
-- MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
-- MAGIC </div>

-- COMMAND ----------

-- MAGIC %md
-- MAGIC # Managing account identities
-- MAGIC 
-- MAGIC In this lab you will learn how to:
-- MAGIC * Create identities in the account console for users and service principals
-- MAGIC * Create groups and manage group memberships
-- MAGIC * Distribute administrative responsibilities

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Overview
-- MAGIC 
-- MAGIC Databricks identity and access management spans both the account and workspaces. Existing Databricks users are probably familiar with workspace-level identities, which were and continue to be used to access services like the Data Science and Engineering Workspace, Databricks SQL, and Databricks Machine Learning, as well as the assets associated with those services. Prior to Unity Catalog, account-level identities had little relevance to most users, since these identities were used only to administer a few basic aspects of the Databricks account. But with the introduction of Unity Catalog and its situation outside of the workspace, the heart of the Databricks identity and access management now lives in the account. It's important to understand the distinction between these two levels of identity and how to manage the relationship between the two.
-- MAGIC 
-- MAGIC Account-level identities, which we focus on in this lab, are managed through the Databricks account console or its associated SCIM APIs. In this lab, we'll focus on account console usage.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Prerequisites
-- MAGIC 
-- MAGIC If you would like to follow along with this lab, you will need account administrator capabilities over your Databricks account, as creating identities is done in the account admininistrator console.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Users and service principals
-- MAGIC 
-- MAGIC In Databricks, a **user** means the same thing for both the account and the workspace: an individual interactively using the system – that is, a person. Users are identified through their email address, and log in using their email address and a password. Users typically interact with the platform through the user interface, though they can also access functionality remotely using APIs or the Databricks CLI. 
-- MAGIC 
-- MAGIC Users who are account administrators log in to the account console, where they can perform administrative tasks and access workspaces. The remaining users  will log in to one of the workspaces to which they are assigned. But, their identity at the account level is still critical in allowing them to access data through Unity Catalog.
-- MAGIC 
-- MAGIC A **service principal**, also the same for both the account and workspace, is an individual entity like a user, but is intended for use with automated tools and running jobs. While they have a name associated with them, they are actually identified through a globally unique identifier (GUID) that is dynamically generated when the identity is created. Service principals authenticate using a token and access functionality through APIs.
-- MAGIC 
-- MAGIC While users can access functionality remotely using APIs or the Databricks CLI, it's recommended to use service principals for automated tasks or jobs that will be running on an ongoing basis.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Creating a user
-- MAGIC Let 's add a new user to our account.
-- MAGIC 
-- MAGIC 1. Log in to the <a href="https://accounts.cloud.databricks.com/" target="_blank">account console</a> as an account administrator.
-- MAGIC 1. In the left sidebar, let's click **User management**. The **Users** tab is shown by default.
-- MAGIC 1. Let's click **Add user**.
-- MAGIC 1. Provide an email address. This is the identifying piece of information that uniquely identifies users across the system. It must be a valid email, since that will be used to confirm identity and manage their password. For the purposes of this training exercise, I am using a temporary email address courtesy of <a href="https://www.dispostable.com/" target="_blank">dispostable.com</a>.
-- MAGIC 1. Provide a first and last name. Though these fields are not used by the system, they make identities more human-readable.
-- MAGIC 1. Click **Send invite**.
-- MAGIC 1. The new user will be issued an email inviting them to join and set their password.
-- MAGIC 
-- MAGIC Though this user has been added to the account, they will not be able to access Databricks services yet since they have not been assigned to any workspaces. However, their addition to the account does make them a valid principal in the eyes of Unity Catalog. Let's validate this now.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC #### Validating user
-- MAGIC 
-- MAGIC Let's check to see that our newly created user can be seen by Unity Catalog.
-- MAGIC 
-- MAGIC 1. From the Data Science and Engineering workspace, go to the <a href="explore/data" target="_blank">Data</a> page (also accessible in the left sidebar).
-- MAGIC 1. Select the **main** catalog, which is created by default in every Unity Catalog metastore.
-- MAGIC 1. Select the **Permissions** tab.
-- MAGIC 1. Click **Grant**.
-- MAGIC 1. Perform a search by typing some element from the identity we just created (name, email address, domain name).
-- MAGIC 
-- MAGIC Notice how the identity appears in the dropdown list. Its availability means that this identity is a valid principal as far Unity Catalog is concerned. It also means that we can start granting privileges on data objects to this user. However, this user can't access any workspaces yet since they're not assigned to any.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Deleting a user
-- MAGIC 
-- MAGIC If a user leaves the organization we can delete them. This will not delete any data objects they own. If we wish to temporarily revoke access (for example, if they are absent for a period of time but will be returning), then users can be deactivated (though this option is only available through <a href="https://docs.databricks.com/dev-tools/api/latest/scim/scim-users.html#activate-and-deactivate-user-by-id" target="_blank">the API</a> at the present time).
-- MAGIC 
-- MAGIC Let's see how to delete a user:
-- MAGIC 1. From the **User management** page of the account console, locate and select the targeted user (using the **Search** field if desired).
-- MAGIC 1. Click the three dots at the top-right corner of the page and select **Delete user** (you will be prompted to confirm but for now you can cancel).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Managing service principals
-- MAGIC 
-- MAGIC The workflow for managing service principals is virtually identical to users. Let's see how to add one now.
-- MAGIC 1. From the **User management** page of the account console, select the **Service principals** tab.
-- MAGIC 1. Let's click **Add service principal**.
-- MAGIC 1. Let's provide a name. Though this isn't an identifying piece of information, it's helpful to use something that will make sense for administrators.
-- MAGIC 1. Click **Add**.
-- MAGIC 
-- MAGIC Service principals are identified by their **Application ID**, which you will see once the service principal is created.
-- MAGIC 
-- MAGIC To delete a service principal:
-- MAGIC 1. In the **Service Principals** tab, locate and select the desired service principal from the list, using the **Search** field if necessary.
-- MAGIC 1. Click the three dots at the top-right corner of the page and select **Delete** (you will be prompted to confirm but for now you can cancel).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Groups
-- MAGIC 
-- MAGIC The concept of groups is pervasive to countless security models, and for good reason. Groups gather individual users (and service principals) into a logical units to simplify management. Groups can also be nested within other groups if needed. Any grants on the group are automatically inherited by all members of the group.
-- MAGIC 
-- MAGIC Data governance policies are generally defined in terms of roles, and groups provide a user management construct that nicely maps to such roles, simplifying the implementation of these governance policies. In this way, permissions can be granted to groups in accordance with your organization’s security policies, and users can be added to groups as per their roles within the organization.
-- MAGIC 
-- MAGIC When users transition between roles, it’s simple to move a user from one group to another. Performing an equivalent operation when permissions are hard-wired at the indivdual user level is significantly more intensive. Likewise, as your governance model evolves and role definitions change, it’s much easier to effect those changes on groups rather than having to replicate changes across a number of individual users.
-- MAGIC 
-- MAGIC For these reasons, we advise implementing groups and granting data permissions to groups rather than individual users or service principals.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Creating a group
-- MAGIC 
-- MAGIC Let's add a new group.
-- MAGIC 
-- MAGIC 1. From the **User management** page of the account console, select the **Groups** tab.
-- MAGIC 1. Click **Add group**.
-- MAGIC 1. Let's give the group the name *analysts*.
-- MAGIC 1. Finally, click **Save**.
-- MAGIC 
-- MAGIC From here we can immediately add members to the new group, but let's skip for now since it's a task that can be done at any time.
-- MAGIC 
-- MAGIC Let's repeat the process to create another new group named *metastore_admins*.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Managing group members
-- MAGIC 
-- MAGIC Let's add the user we created earlier to the *analysts* group we just created.
-- MAGIC 
-- MAGIC 1. In the **Groups** tab, locate and select the *analysts* group, using the **Search** field if desired.
-- MAGIC 1. Click **Add members**.
-- MAGIC 1. From here we can use the searchable text field that also functions as a drop-down menu when clicked. Let's identify the users, service principals or groups we want to add (search for and select user created earlier), then click **Add**. Note that we can add multiple entries at once if needed.
-- MAGIC 
-- MAGIC The group membership takes effect immediately.
-- MAGIC 
-- MAGIC Now let's repeat the process to add ourselves to the *metastore_admins* group that we just created (**do not add the created user we just added to the *analysts* group**). The intent of this group is to simplify the management of metastore administrators, but this action won't actually do anything yet. We'll get to that in the next section.
-- MAGIC 
-- MAGIC Removing a principal from a group is a simple matter.
-- MAGIC 1. Locate and select the group you want to manage in the **Groups** tab.
-- MAGIC 1. Locate the principal, using the **Search** field if desired.
-- MAGIC 1. Click the three dots in the rightmost column.
-- MAGIC 1. Select **Remove** (you will be prompted to confirm but for now you can cancel).
-- MAGIC 
-- MAGIC All principals listed in the group (including child groups) automatically inherit any grants on the group. Assigning privileges in a group-wise fashion like this is considered a data governance best practice since it greatly simplifies the implementation and maintenance of an organization's security model.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Deleting a group
-- MAGIC 
-- MAGIC As your data governance model evolves, it may become necessary to eliminate groups. Deleting groups in Unity Catalog destroys the membership structure and any permissions it conveyed to its members, but it won't recursively delete members, nor will it affect permissions granted directly to those members; only the inherited permissions are impacted.
-- MAGIC 
-- MAGIC In the left sidebar, let's click **Users & Groups**.
-- MAGIC 1. In the **Groups** tab, locate the targeted group, using the **Search** field if desired.
-- MAGIC 1. Click the three dots in the rightmost column.
-- MAGIC 1. Select **Delete** (you will be prompted to confirm but for now you can cancel).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Managing workspace assignments
-- MAGIC 
-- MAGIC Account administrators can assign principals (users and service principals individually, or groups) to one or more workspaces. If a user is assigned to more than one workspace, they will be prompted when logging in, and the navigational sidebar on the left will present them with the ability to switch between workspaces they have access to.
-- MAGIC 
-- MAGIC 1. In the account console, let's click the **Workspaces** icon in the left sidebar.
-- MAGIC 1. Locate and select the targeted workspace, using the **Search** field if desired.
-- MAGIC 1. Select the **Permissions** tab.
-- MAGIC 1. A list of currently assigned principals is displayed. To add more, let's click **Add permissions**.
-- MAGIC 1. Search for a user, service principal, or group to assign (search for *analysts*). 
-- MAGIC 1. The **Permission** dropdown provides the option to add the principal as a regular user or a workspace administrator. Leave this set to *User*.
-- MAGIC 1. Specify additional principals, if desired.
-- MAGIC 1. When done, click **Save**.
-- MAGIC 
-- MAGIC Account administrators can similarly unassign users or service principals from a workspace.
-- MAGIC 1. In the **Workspaces** page, locate and select the targeted workspace, using the **Search** field if desired.
-- MAGIC 1. Select the **Permissions** tab.
-- MAGIC 1. Locate the desired principal, and click the three dots in the rightmost column.
-- MAGIC 1. Select **Remove** (you will be prompted to confirm but for now you can cancel).

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Distributing administrative responsibilities
-- MAGIC 
-- MAGIC By default, Databricks account administrators have a lot of reponsibilities, which include:
-- MAGIC * Creating and managing workspaces and metastores
-- MAGIC * Managing users and groups
-- MAGIC * Providing reports on platform usage and statistics
-- MAGIC * Managing subscription and billing information
-- MAGIC 
-- MAGIC Creating metastores, while it looks like a simple task from the outset, carries with it a whole other set of additional responsibilities relating to data governance. Creating a metastore makes you the owner of the metastore which, in Unity Catalog, means you are the administrator for that metastore. Metastore admins have the following additional responsibilities:
-- MAGIC * Bootstrapping a metastore; only they can do certain important startup tasks, such as:
-- MAGIC   * Creating and managing permissions on catalogs
-- MAGIC   * Managing data objects, if regular users are not permitted to do so under your data governance policies
-- MAGIC * Linking external storage into the metastore
-- MAGIC * Ongoing maintenance and administration
-- MAGIC 
-- MAGIC To avoid bottlenecks, it's useful to delegate or grant some of these capabilities to others in the organization.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Delegating account administration capabilities
-- MAGIC 
-- MAGIC Because account administrators have a lot of responsibilities as mentioned earlier, it's beneficial to distribute the workload to others. This can also help to avoid delays when the primary administrator is unavailable.
-- MAGIC 
-- MAGIC We grant account administration capabilites to a user by enabling a role in their user profile. Let's see how to do this now.
-- MAGIC 
-- MAGIC 1. From the **User management** page of the account console, locate and select the targeted user (using the **Search** field if desired).
-- MAGIC 1. Click the **Roles** tab.
-- MAGIC 1. Enable **Account admin**. This change will take effect immediately.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ### Delegating metastore administration capabilities
-- MAGIC 
-- MAGIC Data governance processes often call for metastore admin intervention. To avoid bottlenecks, it's useful to share metastore administration with others in the organization, rather than limiting it to the individual who created the metastore (by default, an account administrator, who will likely be busy with many other tasks).
-- MAGIC 
-- MAGIC We can change the administrator to another individual (that is, a user or service principal) though that doesn't really solve the problem of potential bottlenecks. For this reason it's usually more convenient to create a group for this purpose and assign metastore administrator to the group.
-- MAGIC 
-- MAGIC 1. In the **Data** page of the account console, select the desired metastore.
-- MAGIC 1. Locate the **Metastore Admin** field. This displays the current administrator.
-- MAGIC 1. Select the **Edit** link.
-- MAGIC 1. Choose a principal that will become the new administrator. We can change administrator to another individual, but that doesn't really solve the bottleneck issue. We would merely be transferring the bottleneck to another individual. It makes more sense to create a group for this purpose and make that group the administrator. This way you can have more than one admin, and you can easily grant or revoke metastore admin capabilities by adding or removing users from the group. For this reason, let's use the *metastore_admins* group we created earlier. Though this group only has one member right now, this gives a lot more flexibility in the future.
-- MAGIC 1. Click **Save**.

-- COMMAND ----------

-- MAGIC %md-sandbox
-- MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
-- MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
-- MAGIC <br/>
-- MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>