# Databricks notebook source
class DBAcademyHelper():
    def __init__(self, lesson=None, catalog="main"):
        import re, time

        username = spark.sql("SELECT current_user()").first()[0]
        clean_username = re.sub("[^a-zA-Z0-9]", "_", username)

        self.catalog = catalog
        self.schema = f"dbacademy_{clean_username}_{dbutils.widgets.get('schema')}"

        for c in [ self.catalog, "hive_metastore" ]:
            print(f"\nCreating the schema \"{c}.{self.schema}\"")
            spark.sql(f"CREATE SCHEMA IF NOT EXISTS {c}.{self.schema}")

        spark.sql(f"USE CATALOG {self.catalog}")
        spark.sql(f"USE SCHEMA {self.schema}")

        spark.conf.set("da.catalog", self.catalog)
        spark.conf.set("DA.catalog", self.catalog)
        spark.conf.set("da.schema", self.schema)
        spark.conf.set("DA.schema", self.schema)

        
    def cleanup(self):
        for c in [ self.catalog, "hive_metastore" ]:
            print(f"Dropping the schema \"{c}.{self.schema}\"")
            spark.sql(f"DROP SCHEMA IF EXISTS {c}.{self.schema} CASCADE")

da = DBAcademyHelper(catalog=dbutils.widgets.get('catalog'))
