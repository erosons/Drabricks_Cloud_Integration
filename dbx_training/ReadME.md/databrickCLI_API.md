Databricks Account Commands

Usage:
  databricks account [command]

# Identity and Access Management
  access-control            These APIs manage access rules on resources in an account.
  groups                    Groups simplify identity management, making it easier to assign access to Databricks account, data, and other securable objects.
  service-principals        Identities for use with jobs, automated tools, and systems such as scripts, apps, and CI/CD platforms.
  users                     User identities recognized by Databricks and represented by email addresses.
  workspace-assignment      The Workspace Permission Assignment API allows you to manage workspace permissions for principals in your account.

# Unity Catalog
  metastore-assignments     These APIs manage metastore assignments to a workspace.
  metastores                These APIs manage Unity Catalog metastores for an account.
  storage-credentials       These APIs manage storage credentials for a particular metastore.

# Settings
  ip-access-lists           The Accounts IP Access List API enables account admins to configure IP access lists for access to the account console.
  network-connectivity      These APIs provide configurations for the network connectivity of your workspaces for serverless compute resources.
  settings                  Accounts Settings API allows users to manage settings at the account level.

# Provisioning
  credentials               These APIs manage credential configurations for this workspace.
  encryption-keys           These APIs manage encryption key configurations for this workspace (optional).
  networks                  These APIs manage network configurations for customer-managed VPCs (optional).
  private-access            These APIs manage private access settings for this account.
  storage                   These APIs manage storage configurations for this workspace.
  vpc-endpoints             These APIs manage VPC endpoint configurations for this account.
  workspaces                These APIs manage workspaces for this account.

# Billing
  billable-usage            This API allows you to download billable usage logs for the specified account and date range.
  budgets                   These APIs manage budget configurations for this account.
  log-delivery              These APIs manage log delivery configurations for this account.
  usage-dashboards          These APIs manage usage dashboards for this account.

# OAuth
  custom-app-integration    These APIs enable administrators to manage custom OAuth app integrations, which is required for adding/using Custom OAuth App Integration like Tableau Cloud for Databricks in AWS cloud.
  o-auth-published-apps     These APIs enable administrators to view all the available published OAuth applications in Databricks.
  published-app-integration These APIs enable administrators to manage published OAuth app integrations, which is required for adding/using Published OAuth App Integration like Tableau Desktop for Databricks in AWS cloud.
  service-principal-secrets These APIs enable administrators to manage service principal secrets.

Flags:
  -h, --help   help for account

Global Flags:
      --debug            enable debug logging
  -o, --output type      output type: text or json (default text)
  -p, --profile string   ~/.databrickscfg profile
  -t, --target string    bundle target to use (if applicable)
# #######################
Databricks CLI
# #####################
Usage:
  databricks [command]

# Databricks Workspace
  fs                                     Filesystem related commands
  git-credentials                        Registers personal access token for Databricks to do operations on behalf of the user.
  repos                                  The Repos API allows users to manage their git repos.
  secrets                                The Secrets API allows you to manage secrets, secret scopes, and access permissions.
  workspace                              The Workspace API allows you to list, import, export, and delete notebooks and folders.

# Compute
  cluster-policies                       You can use cluster policies to control users' ability to configure clusters based on a set of rules.
  clusters                               The Clusters API allows you to create, start, edit, list, terminate, and delete clusters.
  global-init-scripts                    The Global Init Scripts API enables Workspace administrators to configure global initialization scripts for their workspace.
  instance-pools                         Instance Pools API are used to create, edit, delete and list instance pools by using ready-to-use cloud instances which reduces a cluster start and auto-scaling times.
  instance-profiles                      The Instance Profiles API allows admins to add, list, and remove instance profiles that users can launch clusters with.
  libraries                              The Libraries API allows you to install and uninstall libraries and get the status of libraries on a cluster.
  policy-compliance-for-clusters         The policy compliance APIs allow you to view and manage the policy compliance status of clusters in your workspace.
  policy-families                        View available policy families.

# Workflows
  jobs                                   The Jobs API allows you to create, edit, and delete jobs.
  policy-compliance-for-jobs             The compliance APIs allow you to view and manage the policy compliance status of jobs in your workspace.

# Delta Live Tables
  pipelines                              The Delta Live Tables API allows you to create, edit, delete, start, and view details about pipelines.

# Machine Learning
  experiments                            Experiments are the primary unit of organization in MLflow; all MLflow runs belong to an experiment.
  model-registry                         Note: This API reference documents APIs for the Workspace Model Registry.

# Real-time Serving
  serving-endpoints                      The Serving Endpoints API allows you to create, update, and delete model serving endpoints.

# Identity and Access Management
  current-user                           This API allows retrieving information about currently authenticated user or service principal.
  groups                                 Groups simplify identity management, making it easier to assign access to Databricks workspace, data, and other securable objects.
  permissions                            Permissions API are used to create read, write, edit, update and manage access for various users on different objects and endpoints.
  service-principals                     Identities for use with jobs, automated tools, and systems such as scripts, apps, and CI/CD platforms.
  users                                  User identities recognized by Databricks and represented by email addresses.

# Databricks SQL
  alerts                                 The alerts API can be used to perform CRUD operations on alerts.
  alerts-legacy                          The alerts API can be used to perform CRUD operations on alerts.
  dashboards                             In general, there is little need to modify dashboards using the API.
  data-sources                           This API is provided to assist you in making new query objects.
  queries                                The queries API can be used to perform CRUD operations on queries.
  queries-legacy                         These endpoints are used for CRUD operations on query definitions.
  query-history                          A service responsible for storing and retrieving the list of queries run against SQL endpoints and serverless compute.
  warehouses                             A SQL warehouse is a compute resource that lets you run SQL commands on data objects within Databricks SQL.

# Unity Catalog
  artifact-allowlists                    In Databricks Runtime 13.3 and above, you can add libraries and init scripts to the allowlist in UC so that users can leverage these artifacts on compute configured with shared access mode.
  catalogs                               A catalog is the first layer of Unity Catalog’s three-level namespace.
  connections                            Connections allow for creating a connection to an external data source.
  external-locations                     An external location is an object that combines a cloud storage path with a storage credential that authorizes access to the cloud storage path.
  functions                              Functions implement User-Defined Functions (UDFs) in Unity Catalog.
  grants                                 In Unity Catalog, data is secure by default.
  metastores                             A metastore is the top-level container of objects in Unity Catalog.
  model-versions                         Databricks provides a hosted version of MLflow Model Registry in Unity Catalog.
  online-tables                          Online tables provide lower latency and higher QPS access to data from Delta tables.
  quality-monitors                       A monitor computes and monitors data or model quality metrics for a table over time.
  registered-models                      Databricks provides a hosted version of MLflow Model Registry in Unity Catalog.
  resource-quotas                        Unity Catalog enforces resource quotas on all securable objects, which limits the number of resources that can be created.
  schemas                                A schema (also called a database) is the second layer of Unity Catalog’s three-level namespace.
  storage-credentials                    A storage credential represents an authentication and authorization mechanism for accessing data stored on your cloud tenant.
  system-schemas                         A system schema is a schema that lives within the system catalog.
  table-constraints                      Primary key and foreign key constraints encode relationships between fields in tables.
  tables                                 A table resides in the third layer of Unity Catalog’s three-level namespace.
  temporary-table-credentials            Temporary Table Credentials refer to short-lived, downscoped credentials used to access cloud storage locationswhere table data is stored in Databricks.
  volumes                                Volumes are a Unity Catalog (UC) capability for accessing, storing, governing, organizing and processing files.
  workspace-bindings                     A securable in Databricks can be configured as __OPEN__ or __ISOLATED__.

# Delta Sharing
  providers                              A data provider is an object representing the organization in the real world who shares the data.
  recipient-activation                   The Recipient Activation API is only applicable in the open sharing model where the recipient object has the authentication type of TOKEN.
  recipients                             A recipient is an object you create using :method:recipients/create to represent an organization which you want to allow access shares.
  shares                                 A share is a container instantiated with :method:shares/create.

# Settings
  ip-access-lists                        IP Access List enables admins to configure IP access lists.
  notification-destinations              The notification destinations API lets you programmatically manage a workspace's notification destinations.
  settings                               Workspace Settings API allows users to manage settings at the workspace level.
  token-management                       Enables administrators to get all tokens and delete tokens for other users.
  tokens                                 The Token API allows you to create, list, and revoke tokens that can be used to authenticate and access Databricks REST APIs.
  workspace-conf                         This API allows updating known workspace settings for advanced users.

# Developer Tools
  bundle                                 Databricks Asset Bundles let you express data/AI/analytics projects as code.
  sync                                   Synchronize a local directory to a workspace directory

# Vector Search
  vector-search-endpoints                **Endpoint**: Represents the compute resources to host vector search indexes.
  vector-search-indexes                  **Index**: An efficient representation of your embedding vectors that supports real-time and efficient approximate nearest neighbor (ANN) search queries.

# Dashboards
  lakeview                               These APIs provide specific management operations for Lakeview dashboards.

# Marketplace
  consumer-fulfillments                  Fulfillments are entities that allow consumers to preview installations.
  consumer-installations                 Installations are entities that allow consumers to interact with Databricks Marketplace listings.
  consumer-listings                      Listings are the core entities in the Marketplace.
  consumer-personalization-requests      Personalization Requests allow customers to interact with the individualized Marketplace listing flow.
  consumer-providers                     Providers are the entities that publish listings to the Marketplace.
  provider-exchange-filters              Marketplace exchanges filters curate which groups can access an exchange.
  provider-exchanges                     Marketplace exchanges allow providers to share their listings with a curated set of customers.
  provider-files                         Marketplace offers a set of file APIs for various purposes such as preview notebooks and provider icons.
  provider-listings                      Listings are the core entities in the Marketplace.
  provider-personalization-requests      Personalization requests are an alternate to instantly available listings.
  provider-provider-analytics-dashboards Manage templated analytics solution for providers.
  provider-providers                     Providers are entities that manage assets in Marketplace.

Apps
  apps                                   Apps run directly on a customer’s Databricks instance, integrate with their data, use and extend Databricks services, and enable users to interact through single sign-on.
  apps                                   Apps run directly on a customer’s Databricks instance, integrate with their data, use and extend Databricks services, and enable users to interact through single sign-on.

Additional Commands:
  account                                Databricks Account Commands
  api                                    Perform Databricks API call
  auth                                   Authentication related commands
  completion                             Generate the autocompletion script for the specified shell
  configure                              Configure authentication
  help                                   Help about any command
  labs                                   Manage Databricks Labs installations
  version                                Retrieve information about the current version of this CLI

# Permissions API are used to create read, write, edit, update and manage access
  for various users on different objects and endpoints.
  
  * **[Apps permissions](:service:apps)** — Manage which users can manage or
  use apps.
  
  * **[Cluster permissions](:service:clusters)** — Manage which users can
  manage, restart, or attach to clusters.
  
  * **[Cluster policy permissions](:service:clusterpolicies)** — Manage which
  users can use cluster policies.
  
  * **[Delta Live Tables pipeline permissions](:service:pipelines)** — Manage
  which users can view, manage, run, cancel, or own a Delta Live Tables
  pipeline.
  
  * **[Job permissions](:service:jobs)** — Manage which users can view,
  manage, trigger, cancel, or own a job.
  
  * **[MLflow experiment permissions](:service:experiments)** — Manage which
  users can read, edit, or manage MLflow experiments.
  
  * **[MLflow registered model permissions](:service:modelregistry)** — Manage
  which users can read, edit, or manage MLflow registered models.
  
  * **[Password permissions](:service:users)** — Manage which users can use
  password login when SSO is enabled.
  
  * **[Instance Pool permissions](:service:instancepools)** — Manage which
  users can manage or attach to pools.
  
  * **[Repo permissions](repos)** — Manage which users can read, run, edit, or
  manage a repo.
  
  * **[Serving endpoint permissions](:service:servingendpoints)** — Manage
  which users can view, query, or manage a serving endpoint.
  
  * **[SQL warehouse permissions](:service:warehouses)** — Manage which users
  can use or manage SQL warehouses.
  
  * **[Token permissions](:service:tokenmanagement)** — Manage which users can
  create or use tokens.
  
  * **[Workspace object permissions](:service:workspace)** — Manage which
  users can read, run, edit, or manage alerts, dbsql-dashboards, directories,
  files, notebooks and queries.
  
  For the mapping of the required permissions for specific actions or abilities
  and other important information, see [Access Control].
  
  Note that to manage access control on service principals, use **[Account
  Access Control Proxy](:service:accountaccesscontrolproxy)**.
  
  [Access Control]: https://docs.databricks.com/security/auth-authz/access-control/index.html

Usage:
  databricks permissions [command]

Available Commands
  get                   Get object permissions.
  set                   Set object permissions.
  update                Update object permissions.

# REQUEST_OBJECT_TYPE: The type of the request object. Can be one of the following: 
   alerts,authorization, clusters, cluster-policies, dashboards, dbsql-dashboards,
      directories, experiments, files, instance-pools, jobs, notebooks,
      pipelines, queries, registered-models, repos, serving-endpoints, or
      warehouses

Permission Commands
  get-permission-levels Get object permission levels.

Flags:
      --debug            enable debug logging
  -h, --help             help for databricks
  -o, --output type      output type: text or json (default text)
  -p, --profile string   ~/.databrickscfg profile
  -t, --target string    bundle target to use (if applicable)
  -v, --version          version for databricks

Use "databricks [command] --help" for more information about a command.