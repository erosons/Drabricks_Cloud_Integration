%python
import requests
from datetime import timedelta as td
from datetime import datetime as dt
from pyspark.sql.functions import *
import os

BASELINE_FILE = "2015-01-01-15.json.gz"
counters = 0

def download_file(file) -> str:
    global counters

    with requests.Session() as session:
        res = session.get(url=f"https://data.gharchive.org/{file}")
        if res.status_code == 200:
            local_path = f'/tmp/{file}'
            file_path = f'/mnt/engineering/gharchive/{file}'
            dbutils.fs.mkdirs(os.path.dirname(file_path))  # Ensure the directory exists
            
            # Write the content to a local file first
            with open(local_path, 'wb') as fp:
                fp.write(res.content)
            
            # Copy the local file to DBFS
            dbutils.fs.cp(f"file:{local_path}", file_path)
            
            # Optionally, remove the local file if you want to clean up
            os.remove(local_path)
            
            return file_path
        else:
            print(f"Invalid file name or downloads caught up till {file}")
            return None

def get_next_file_name(prev_file_name):
    dt_part = prev_file_name.split(".")[0]
    next_file = f"{dt.strftime(dt.strptime(dt_part, '%Y-%m-%d-%H') + td(hours=1), '%Y-%m-%d-%H')}.json.gz"
    return next_file

def main():
    global counters
    while True:
        file_name = get_next_file_name(BASELINE_FILE)
        file_path = download_file(file_name)
        if file_path:
            df = spark.read.json(file_path)
            df.createOrReplaceTempView("gh_archive")
            sql = "SELECT * FROM gh_archive"
            df = spark.sql(sql)
            counters += 1
            display(df.limit(10))
            if df is not None:
                df.write.format('parquet').partitionBy("id").mode("overwrite").save(f'/mnt/engineering/gh-archive00_{counters}')
            else:
                pass
        else:
            break

main()