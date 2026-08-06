import msal
import requests
import os
from pprint import pprint

# Configuration
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
TENANT_ID = os.getenv('TENANT_ID')
AUTHORITY_URL = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPE = ['https://management.azure.com/.default']  # Databricks API scope
DATABRICKS_INSTANCE = os.getenv('databricks_URL') # e.g., "https://<your-databricks-workspace>.azuredatabricks.net"

# MSAL app instance
msal_app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY_URL,
    client_credential=CLIENT_SECRET
)

def get_access_token():
    """
    Get an access token using the Service Principal credentials.
    """
    # Firstly, looks up a token from cache use token for the current app, NOT for an end user,
    # hence we use account parameter as None
    result =None
    result = msal_app.acquire_token_for_client(scopes=SCOPE)
    if 'access_token' in result:
        print(result['access_token'])
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
    response = requests.get(f'{DATABRICKS_INSTANCE}/api/2.1/clusters/list', headers=headers)
    response.raise_for_status()
    pprint(response.json())
