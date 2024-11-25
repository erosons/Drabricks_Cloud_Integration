from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.sensors.s3_key import S3KeySensor
from airflow.utils.dates import days_ago
import boto3
import requests 
import pandas as pd
from io import BytesIO

# Replace with your configurations
AWS_REGION = "us-east-1"
IAM_ROLE =
S3_BUCKET = "your-s3-bucket-name"
S3_PARQUET_PATH = "data/api_parquet/"
API_ENDPOINT = "https://data.gharchive.org"
GLUE_JOB_NAME = "your-glue-job-name"
ICEBERG_DATABASE = "your_database"
ICEBERG_TABLE = "your_table"

# Function to read API data and save as Parquet
def fetch_and_store_api_data():
    with requests.Session() as session:
        response = session.get(url=f"{API_ENDPOINT}/{file}")
        response.raise_for_status()
        data = response.json()
        
        # Convert JSON to DataFrame
        df = pd.DataFrame(data)
        
        # Save DataFrame to Parquet file in S3
        parquet_buffer = BytesIO()
        df.to_parquet(parquet_buffer, index=False, engine='pyarrow')
        parquet_buffer.seek(0)
        
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=f"{S3_PARQUET_PATH}data.parquet",
            Body=parquet_buffer.getvalue(),
        )

# Function to create or update Glue job
def create_or_update_glue_job():
    glue_client = boto3.client('glue', region_name=AWS_REGION)
    #script_location = f"s3://{S3_BUCKET}/scripts/glue_job_script.py"
    script_location = f"/dags/glue-jobs/amperon/glue_job_scripts.py"
    try:
        # Create Glue Job if it doesn't exist
        glue_client.create_job(
            Name=GLUE_JOB_NAME,
            Role=IAM_ROLE,
            Command={
                "Name": "glueetl",
                "ScriptLocation": script_location,
                "PythonVersion": "3"
            },
            DefaultArguments={
                "--enable-glue-datacatalog": "true",
                "--job-bookmark-option": "job-bookmark-disable",
            },
            MaxRetries=2,
            Timeout=2880,
            GlueVersion="3.0",
            MaxCapacity=2.0,  # Adjust based on the job requirements
        )
        print(f"Glue job '{GLUE_JOB_NAME}' created successfully.")
    except glue_client.exceptions.AlreadyExistsException:
        # Update Glue Job if it exists
        glue_client.update_job(
            JobName=GLUE_JOB_NAME,
            JobUpdate={
                "Role": IAM_ROLE,
                "Command": {
                    "Name": "glueetl",
                    "ScriptLocation": script_location,
                    "PythonVersion": "3"
                },
                "DefaultArguments": {
                    "--enable-glue-datacatalog": "true",
                    "--job-bookmark-option": "job-bookmark-disable",
                },
                "MaxRetries": 2,
                "Timeout": 2880,
                "GlueVersion": "3.0",
                "MaxCapacity": 2.0,  # Adjust based on the job requirements
            },
        )
        print(f"Glue job '{GLUE_JOB_NAME}' updated successfully.")

# Function to trigger Glue job
def trigger_glue_job():
    glue_client = boto3.client('glue', region_name=AWS_REGION)
    response = glue_client.start_job_run(JobName=GLUE_JOB_NAME)
    print(f"Glue job triggered. Run ID: {response['JobRunId']}")

# Default arguments for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

# DAG definition
with DAG(
    "api_to_s3_to_iceberg",
    default_args=default_args,
    description="ETL pipeline: API to S3 to Iceberg",
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
) as dag:

    # Task 1: Fetch API data and store as Parquet in S3
    fetch_api_task = PythonOperator(
        task_id="fetch_api_data",
        python_callable=fetch_and_store_api_data,
    )

    # Task 2: Sensor to check if Parquet file exists in S3
    s3_sensor_task = S3KeySensor(
        task_id="check_s3_file",
        bucket_name=S3_BUCKET,
        bucket_key=f"{S3_PARQUET_PATH}data.parquet",
        aws_conn_id="aws_default",
        timeout=60 * 10,
        poke_interval=30,
    )

    # Task 3: Create or Update Glue job
    create_glue_job_task = PythonOperator(
        task_id="create_glue_job",
        python_callable=create_or_update_glue_job,
    )

    # Task 4: Trigger Glue job to create Iceberg table
    glue_job_task = PythonOperator(
        task_id="trigger_glue_job",
        python_callable=trigger_glue_job,
    )

    # Task dependencies
    fetch_api_task >> s3_sensor_task >> create_glue_job_task >> glue_job_task
