## ######################
# USING Mutiselect Widget
#########################
%python
dbutils.widgets.multiselect(
    name="cols",
    defaultValue="RowID",
    choices=["RowID", "OrderID", "OrderDate", "ShipDate", "Discount", "Profit"]
)

%python
selected_cols = dbutils.widgets.get("cols")
print(selected_cols)

%python
# You can use the selected columns in your DataFrame operations
df = spark.read.format("csv").option("header", "true").load("/path/to/your/csvfile")
selected_cols_list = selected_cols.split(",")
df_selected = df.select(*selected_cols_list)
display(df_selected)


## ######################
# USING  DROPDOWN Widget
## ######################
%python
dbutils.widgets.dropdown("year", "2015", ["2015","2016","2017","2018","2019"])

%sql
SELECT * FROM sample_superstore_in 
where year(OrderDate) ==${year} | :year   # change the value in the dropdown


## ###################
# USING  TEXT Widget
## ###################
%python
dbutils.widgets.text("yearValue", "2015")

%sql
SELECT * FROM sample_superstore_in 
where year(OrderDate) ==${yearValue}|:yearValue