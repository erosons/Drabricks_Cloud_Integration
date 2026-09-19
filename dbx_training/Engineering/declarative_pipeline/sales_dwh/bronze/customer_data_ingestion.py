from pyspark import pipelines as dp
from pyspark.sql import functions as F
from importlib.resources import files, as_file
from Utilities.yaml_parser import load_yaml
import json
import os

# Known issues with declarative pipelines:
# - __fiile__ is not supported__
# - dump of yaml in single line is not supported__

# dq_path  = files("Utilities").joinpath("dq.yml")
# # base_dir = os.path.dirname(__file__)
# dq_path = os.path.join(base_dir, "Utilities", "dq.yml")

dq_path  = '/Workspace/Users/eromonsei.o.samson@gopherwood.org/Drabricks_Cloud_Integration/Databricks-practice/Engineering/declarative_pipeline/Utilities/dq.yml'
dq_rules = load_yaml(dq_path)
print(dq_rules)
drop_rules = dq_rules.get("drop_rules")
rules =  dq_rules.get("rules")

# Handles scenario were multiple sources are feeding into a single table

# rules = {"rule_1":"id IS NOT Null", "rule_2":"last_name IS NOT Null", "rule_3":"first_name IS NOT Null" }
# drop_rules ={"rule_4": "attachments IS NOT Null" }

dp.create_streaming_table(
    name="customers",
    expect_all=rules,
    expect_all_or_drop=drop_rules,
    table_properties={
        "pipelines.owner": "pipelines",
        "quality": "bronze",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.enableDeletionVectors": "true"
        }
    )

#feed 1 in customer_region1
@dp.append_flow(target = "customers")
def customer_region1():
  return (
    spark.readStream.table("mysandbox.dl_northwind.customer_region1")
  )

#feed 2 in customer_region2
@dp.append_flow(target = "customers")
def customer_region2():
  return (
    spark.readStream.table("mysandbox.dl_northwind.customer_region2")
  )
