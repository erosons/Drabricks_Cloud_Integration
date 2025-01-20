from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (NotebookTask, Source, Task)
from databricks.sdk.service.jobs import TaskDependency
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
job_description = """
                   New job
                   """

# Create a workspace client
w = WorkspaceClient()
# Retrieve user information from environment variables
user = os.getenv('myuser')  # Ensure 'USER' is set in your environment variables


start_time = time.time()
    
# Define a new cluster configuration using an instance pool
resp = w.clusters.create_and_wait(
        cluster_name=f'my-cluster',
        spark_version='12.2.x-scala2.12',
        instance_pool_id='1024-180105-mauls20-pool-me54pjpu',
        num_workers=1
    )
logging.info(resp)
# Create the job with the new cluster configuration
logging.info('Creating cluster')
j = w.jobs.create(
        name=f"My Serverless Job_",
        tasks=[
            Task(
                description = job_description ,
                existing_cluster_id = resp.cluster_id,
                notebook_task=NotebookTask(
                    notebook_path=f"/Users/{user}/myjob1",
                    source=Source("WORKSPACE")
                ),
                task_key="MyTask",
                #new_cluster=new_cluster  # Attach the cluster configuration to the task
            ),
            Task(
                description = job_description ,
                existing_cluster_id = resp.cluster_id,
                notebook_task=NotebookTask(
                    notebook_path=f"/Users/{user}/myjob1",
                    source=Source("WORKSPACE")
                ),
                task_key="MyTask2",
                #new_cluster=new_cluster  # Attach the cluster configuration to the task
            ),
            Task(
                description = job_description ,
                existing_cluster_id = resp.cluster_id,
                notebook_task=NotebookTask(
                    notebook_path=f"/Users/{user}/myjob1",
                    source=Source("WORKSPACE")
                ),
                task_key="MyTask3",
                depends_on =[TaskDependency(task_key="MyTask2")]
                #new_cluster=new_cluster  # Attach the cluster configuration to the task
            )
        ],
        max_concurrent_runs=1,
        tags={'ETL':'Marketing'}
    )

logging.info("# Trigger the job immediately")
w.jobs.run_now(j.job_id)

time.sleep(10)

# Function to check job status
def is_job_completed(job_id):
    job_runs = w.jobs.list_runs(job_id=job_id, active_only=True)
    # Convert the generator to a list once
    job_runs_list = list(job_runs)
    print(job_runs_list)
    if  len(job_runs_list)>0:  
        RunState =job_runs_list[0].state
        lifecycle_state= RunState.life_cycle_state
        print(lifecycle_state)
        if not str(lifecycle_state) == 'RunLifeCycleState.RUNNING':
            return  True # No active runs, job is considered completed
        else:
            return False # Active job exists
    else:
        return True


# Poll job status until it completes
while not is_job_completed(j.job_id):
    logging.info(f"Polling job Status" ,is_job_completed(j.job_id))
    time.sleep(10) 
logging.info("Job has completed.")


# Function to terminate a cluster
w.clusters.delete(resp.cluster_id)
print(f"Cluster {resp.cluster_id} has been terminated.")


end_time = time.time()
duration =end_time-start_time
logging.info('CFinished creating Cluster',duration,j)