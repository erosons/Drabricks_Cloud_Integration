import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import msal
import requests
from pprint import pprint

# Load environment variables

# Configuration
TENANT_ID = os.getenv('TENANT_ID')
VAULT_URL = os.getenv('VAULT_URL')  # URL of the Azure Key Vault, e.g., "https://<your-key-vault-name>.vault.azure.net/"
DATABRICKS_INSTANCE = os.getenv('DATABRICKS_INSTANCE')  # e.g., "https://<your-databricks-workspace>.azuredatabricks.net"

# # Azure Key Vault client
# credential = DefaultAzureCredential()
# secret_client = SecretClient(vault_url=VAULT_URL, credential=credential)

# def get_secret(secret_name):
#     """
#     Retrieve a secret's value from Azure Key Vault.
#     """
#     secret = secret_client.get_secret(secret_name)
#     return secret.value

# Retrieve CLIENT_ID and CLIENT_SECRET from Azure Key Vault
# CLIENT_ID = get_secret("CLIENT-ID-SECRET-NAME")  # Replace with your secret name for Client ID
# CLIENT_SECRET = get_secret("CLIENT-SECRET-NAME")  # Replace with your secret name for Client Secret

# MSAL app instance for authentication
AUTHORITY_URL = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPE = ['https://management.azure.com/.default']
msal_app = msal.ConfidentialClientApplication(
    #CLIENT_ID,
    #CLIENT_ID,
    authority=AUTHORITY_URL,
    #client_credential=CLIENT_SECRET
    client_credential=CLIENT_SECRET
)

def get_access_token():
    """
    Get an access token using the Service Principal credentials.
    """
    result = msal_app.acquire_token_for_client(scopes=SCOPE)
    if 'access_token' in result:
        return result['access_token']
    else:
        raise Exception('Failed to acquire access token: ' + result.get('error_description', 'Unknown error'))

def list_databricks_clusters():
    """
    List clusters in the Databricks workspace.
    """
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    response = requests.get(f'{DATABRICKS_INSTANCE}/api/2.0/clusters/list', headers=headers)
    response.raise_for_status()
    pprint(response.json())

def create_databricks_cluster(cluster_name, spark_version, node_type_id, num_workers):
    """
    Create a new cluster in the Databricks workspace.
    """
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    data = {
        "cluster_name": cluster_name,
        "spark_version": spark_version,
        "node_type_id": node_type_id,
        "num_workers": num_workers
    }
    response = requests.post(f'{DATABRICKS_INSTANCE}/api/2.0/clusters/create', headers=headers, json=data)
    response.raise_for_status()
    pprint(response.json())

# Example usage
if __name__ == '__main__':
    # List clusters
    list_databricks_clusters()

    # Create a new cluster (replace with your configuration)
    # create_databricks_cluster(
    #     cluster_name="ExampleCluster",
    #     spark_version="7.3.x-scala2.12",
    #     node_type_id="Standard_DS3_v2",
    #     num_workers=2
    # )
