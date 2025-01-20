Write all your dependences application or called them boiler plates
And then the main app its which is your data/application Apps.

## Boiler plates (which should be zipped)
  - process.py
  - read.py
  - util.py
  - write.py

## the Main
  app.py

Implementation 

zip -r application-deployment.zip <list of all .py boiler >
Then cp all .zip and them Main.py(app.py) to implementation Path in Databricl dbfs 

## Next
-> databricks fs  mkdirs dbfs:/jobs
-> databricks fs  mkdirs dbfs:/jobs/deployments

## COPY  -> .zip and main files to db location

databricks fs  cp '/home/samson/Desktop/my_sandbox_new/Databricks/spark-submit-dbundled/application-deployment.zip'  dbfs:/jobs/deployments

# Create a Job building a Spark Submit Job in the UI from raw - Staging Zone
Configure -> Spark-sumbit parameters sections
["--py-files", "dbfs:/jobs/deployments/application-deployment.zip","dbfs:/jobs/deployments/app.py"]

## Configure the cluster Size
- Select appropriate workers
- attach IAM for AWS bucket access
- SparK RUNTIME variables
  -  env = os.environ.get('ENVIRON')
     src_dir = os.environ.get('SRC_DIR')
     file_pattern = f"{os.environ.get('SRC_FILE_PATTERN')}-*"
     src_file_format = os.environ.get('SRC_FILE_FORMAT')
     tgt_dir = os.environ.get('TGT_DIR')
     tgt_file_format = os.environ.get('TGT_FILE_FORMAT')

## Example
    PYSPARK_PYTHON=/databricks/python3/bin/python3
    ENVIRON=DATABRICKS
    SRC_DIR=s3://acm-test-bucket/sandbox/
    SRC_FILE_PATTERN=2024-09-30
    SRC_FILE_FORMAT=json
    TGT_DIR=dbfs:/mnt/landing
    TGT_FILE_FORMAT=json


# ################################
### Inititalize job from CLI
# ###############################

Extract an excuted spark job template, using

>>> databricks job get --job-id <no>  > template.json
Pipe in a json pipe, Edit and only Keep the  "settings" value part of the Json

## Reset the job-Id configuration parameters in json payload file using 

>>> databricks jobs reset --job-id 303357717964726 --json-file '/home/samson/Desktop/my_sandbox_new/Databricks/spark-submit-dbundled/sparksubmit_cli_createjob.json'

## Validate 

>>> databricks jobs get --job-id  <jobid>

## Run the Job

databricks jobs run-now --job-id 303357717964726

## Monitor Job runs
>>> databricks runs list

