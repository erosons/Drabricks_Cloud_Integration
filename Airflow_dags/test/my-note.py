
%python
dbutils.widgets.text("yearValue", "2015")

%sql
SELECT * FROM sample_superstore_in 
where year(OrderDate) ==:yearValue
