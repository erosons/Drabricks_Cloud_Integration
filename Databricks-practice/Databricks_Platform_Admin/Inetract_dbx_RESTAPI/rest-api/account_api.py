import requests
# https://docs.databricks.com/api/azure/workspace/secrets/createscope
class AzureDatabricksAccountAPI:
    """
    Python client for Azure Databricks Account REST API.
    """

    def __init__(self, host, account_id, token):
        """
        Initialize the API client.
        :param host: Azure Databricks account login URL.
        :param account_id: Azure Databricks account ID.
        :param token: Azure AD token or personal access token for authentication.
        """
        self.host = host.rstrip("/")
        self.account_id = account_id
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _get_url(self, endpoint):
        """
        Generate full URL for the API endpoint.
        """
        return f"{self.host}/api/2.0/accounts/{self.account_id}/{endpoint}"

    def list_users(self):
        """
        List all users in the account.
        """
        url = self._get_url("scim/v2/Users")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_user(self, email, display_name):
        """
        Create a new user in the account.
        :param email: User email address.
        :param display_name: Display name of the user.
        """
        url = self._get_url("scim/v2/Users")
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "displayName": display_name,
            "active": True
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def delete_user(self, user_id):
        """
        Delete a user from the account.
        :param user_id: ID of the user to delete.
        """
        url = self._get_url(f"scim/v2/Users/{user_id}")
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        return response.status_code == 204

    def list_workspaces(self):
        """
        List all workspaces in the account.
        """
        url = self._get_url("workspaces")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_workspace(self, workspace_name, region, pricing_tier):
        """
        Create a new workspace.
        :param workspace_name: Name of the workspace.
        :param region: Azure region for the workspace.
        :param pricing_tier: Pricing tier (e.g., premium, standard).
        """
        url = self._get_url("workspaces")
        payload = {
            "workspace_name": workspace_name,
            "region": region,
            "pricing_tier": pricing_tier
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def delete_workspace(self, workspace_id):
        """
        Delete a workspace.
        :param workspace_id: ID of the workspace to delete.
        """
        url = self._get_url(f"workspaces/{workspace_id}")
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        return response.status_code == 204

    def list_metastores(self):
        """
        List all metastores in the account.
        """
        url = self._get_url("unity-catalog/metastores")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_metastore(self, name, storage_root):
        """
        Create a new metastore.
        :param name: Name of the metastore.
        :param storage_root: Root storage path for the metastore.
        """
        url = self._get_url("unity-catalog/metastores")
        payload = {
            "name": name,
            "storage_root": storage_root
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def delete_metastore(self, metastore_id):
        """
        Delete a metastore.
        :param metastore_id: ID of the metastore to delete.
        """
        url = self._get_url(f"unity-catalog/metastores/{metastore_id}")
        response = requests.delete(url, headers=self.headers)
        response.raise_for_status()
        return response.status_code == 204

    def get_usage_dashboard(self):
        """
        Retrieve usage dashboard details.
        """
        url = self._get_url("usage")
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    

databricks_api = AzureDatabricksAccountAPI(
    host="https://accounts.azuredatabricks.net",
    account_id="your_account_id",
    token="your_azure_ad_token"
)


users = databricks_api.list_users()
print(users)

workspace = databricks_api.create_workspace(
    workspace_name="my_workspace",
    region="eastus",
    pricing_tier="premium"
)
print(workspace)

success = databricks_api.delete_workspace(workspace_id="workspace_id")
print("Workspace deleted:", success)

metastores = databricks_api.list_metastores()
print(metastores)


metastore = databricks_api.create_metastore(
    name="my_metastore",
    storage_root="abfss://<container>@<storage_account>.dfs.core.windows.net/"
)
print(metastore)


usage = databricks_api.get_usage_dashboard()
print(usage)
