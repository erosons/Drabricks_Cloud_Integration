from delta.tables import (DataFrame,
                          DeltaTable)

from delta_reader import spark


def delta_table():
  delta_table = DeltaTable.forPath(spark, "s3://extertables-loc/project1/")
  return delta_table

"""
Use the function to get history point time sampleshots
"""
def delta_lake_history():
   deltatable = delta_table()
   return  deltatable.history().show()

def restoreToVersion(arg):
   """
   using version number to restore delta lake to a particular version
   """
   deltatable = delta_table()
   return   deltatable.restoreToVersion(arg)

def restoreToTimeStamp(arg):
   """
   using TimeStamp to restore delta lake to a particular version
   """
   delta_table = delta_table()
   return   delta_table.restoreToVersion(arg)

if __name__ == "__main__":
   print(delta_lake_history())