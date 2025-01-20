#  Access control lists overview
# Setting Permission Types
# https://docs.databricks.com/en/security/auth/access-control/index.html
In Databricks, you can use access control lists (ACLs) to configure permission to access workspace level objects. Workspace admins have the CAN MANAGE permission on all objects in their workspace, which gives them the ability to manage permissions on all objects in their workspaces. Users automatically have the CAN MANAGE permission for objects that they create.

For an example of how to map typical personas to workspace-level permissions, see the Proposal for Getting Started With Databricks Groups and Permissions.

Manage access control lists with folders
You can manage workspace object permissions by adding objects to folders. Objects in a folder inherit all permissions settings of that folder. For example, a user that has the CAN RUN permission on a folder has CAN RUN permission on the alerts in that folder.

If you grant a user access to an object inside the folder, they can view the parent folder’s name, even if they do not have permissions on the parent folder. For example, a notebook named test1.py is in a folder named Workflows. If you grant a user CAN READ on test1.py and no permissions on Workflows, the user can see that the parent folder is named Workflows. The user cannot view or access any other objects in the Workflows folder unless they have been granted permissions on them.

# #######
## NOTE
# #######

Note

Secrets are not redacted from a cluster’s Spark driver log stdout and stderr streams. To protect sensitive data, by default, Spark driver logs are viewable only by users with CAN MANAGE permission on job, single user access mode, and shared access mode clusters. To allow users with CAN ATTACH TO or CAN RESTART permission to view the logs on these clusters, set the following Spark configuration property in the cluster configuration: spark.databricks.acl.needAdminPermissionToViewLogs false.

On No Isolation Shared access mode clusters, the Spark driver logs can be viewed by users with CAN ATTACH TO or CAN MANAGE permission. To limit who can read the logs to only users with the CAN MANAGE permission, set spark.databricks.acl.needAdminPermissionToViewLogs to true.