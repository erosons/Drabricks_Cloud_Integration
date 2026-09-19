# to show version
# %pip show databricks-sdk | grep -oP '(?<=Version: )\S+'

# to show version
# %pip show databricks-sdk | grep -oP '(?<=Version: )\S+'
from databricks.sdk import WorkspaceClient
from pathlib import Path


def workspace_caller():
    """
     Returns: List workspaces
     job-577134795020394-run-1066573569659065-Job_cluster
    """
    w = WorkspaceClient()

    for c in w.clusters.list():
       return  print(c.cluster_name)
    
workspace_caller()



# def dfbs_file_path()->Path:

#     """
#         Retrieve data about galaxies.
#         This task simulates an extraction step in an ETL pipeline.
#         Args:
#             num_galaxies (int): The number of galaxies for which data should be returned.
#             Default is 20. Maximum is 20.
#         Returns:
#             list file Path:
#                 /FileStore
#                 /Volume
#                 /Volumes
#                 /databricks-datasets
#                 /databricks-results
#                 /mnt
#                 /tmp
#                 /user
#                 /volume
#                 /volumes

#         """
#     w = WorkspaceClient()
#     d = w.dbutils.fs.ls('/mnt/mymountadls/')

#     for f in d:
#        print(f.path)

# if __name__ == '__main__':
#    dfbs_file_path()
