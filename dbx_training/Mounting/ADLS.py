# Mounting with SPN
configs = {"fs.azure.account.auth.type": "OAuth",
          "fs.azure.account.oauth.provider.type": "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
          "fs.azure.account.oauth2.client.id": "client/AppID",
          "fs.azure.account.oauth2.client.secret": dbutils.secrets.get(scope="dataengng-scope",key="azuremount"),
          "fs.azure.account.oauth2.client.endpoint": "https://login.microsoftonline.com/<tenantID>/oauth2/token"}
containername ='dataengineering2'
storagename ='mountstg001nosoftdelet'
mountpoint ="/mnt/engineering2"
# Optionally, you can add <directory-name> to the source URI of your mount point.
dbutils.fs.mount(
  source = "abfss://"+containername+"@"+storagename+".dfs.core.windows.net/", # azure storage account
  mount_point = mountpoint,
  extra_configs = configs)

# Optionally, mounting with SAS
containername ='dataengineering'
storagename ='dbdlsuseat001'
mountpoint ="/mnt/engineering"
sas ='<containerSAS_token'
dbutils.fs.mount(
  source = "wasbs://"+containername+"@"+storagename+".blob.core.windows.net", # azure storage account
  mount_point = mountpoint,
  extra_configs = {"fs.azure.sas." + containername + "." + storagename + ".blob.core.windows.net": sas}
  )

# Optionally, mounting with primary access Key
containername ='azuredbcomtainer'
storagename ='databricksstorageacct2'
mountpoint ="/mnt/engineering/"
access_key=dbutils.secrets.get(scope="data_analyst_scope",key="azuredb-stirage")
dbutils.fs.mount(
  source = "wasbs://"+containername+"@"+storagename+".blob.core.windows.net", # azure storage account
  mount_point = mountpoint,
  extra_configs = {"fs.azure.account.key." + storagename + ".blob.core.windows.net": access_key}
)



# Optionally, mounting with SAS provides a more granular RBAC on the container
containername ='dataengineering'
storagename ='dbdlsuseat001'
mountpoint ="/mnt/engineering"
sas =dbutils.secret.get(scopes='',key='')  # get from key Vault
dbutils.fs.mount(
  source = "wasbs://"+containername+"@"+storagename+".blob.core.windows.net", # azure storage account
  mount_point = mountpoint,
  extra_configs = {"fs.azure.sas." + containername + "." + storagename + ".blob.core.windows.net": sas}
  )


# validate with to confirm the mounting
dbutils.fs.ls("/mnt/mymountadls")