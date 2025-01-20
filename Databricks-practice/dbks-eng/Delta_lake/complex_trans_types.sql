## Learning Objectives
# By the end of this lesson, you should be able to:
# - Use . and : syntax to query nested data
# - Parse JSON strings into structs
# - Flatten and unpack arrays and structs
# - Combine datasets using joins
# - Reshape data using pivot tables


NOTE:
"""
Schema_of_json() returns the schema derived from an example JSON string.
from_json() parses a column containing a JSON string into a struct type using the specified schema.

After we unpack the JSON string to a struct type, let's unpack and flatten all struct fields into columns.

    * unpacking can be used to flattens structs; col_name.* pulls out the subfields of col_name into their own columns.
"""

                   # Key                 Value
# Sample Data :-> UA000000107395968 {"device":"Android","ecommerce":{},"event_name":"main","event_timestamp":1593880872259777,"geo":{"city":"Laredo","state":"TX"},"items":[],"traffic_source":"instagram","user_first_touch_timestamp":1593880872259777,"user_id":"UA000000107397950"}
#############################
## Working with Nested Data
#############################

# %SQL version

        CREATE OR REPLACE TEMPORARY VIEW TEMP events_strings
        AS
        SELECT 
            string(key),string(value)
        FROM events_raw



# %python version

        from pyspark.sql.functions import col

        events_stringsDF = (spark
            .table("events_raw")
            .select(col("key").cast("string"), 
                    col("value").cast("string"))
            )

        display(events_stringsDF)

### Work with Nested Data

    # %SQL version
    SELECT * 
        FROM events_strings 
        WHERE value:event_name = "finalize" 
    ORDER BY key LIMIT 1

    # %python version

        from pyspark.sql.functions import col

        events_stringsDF = events_strings
            .where(col("value:event_name") == "finalize")
            .orderBy("key")
            .limit(1)
        display(events_stringsDF)

### Parse JSON Strings into Structs
    # %SQL version

    1. Use the schema_of_json function to infer the schema of the JSON string, use a row as an example.
        SELECT schema_of_json('{"device":"Linux","ecommerce":{"purchase_revenue_in_usd":1075.5,"total_item_quantity":1,"unique_items":1},"event_name":"finalize","event_previous_timestamp":1593879231210816,"event_timestamp":1593879335779563,"geo":{"city":"Houston","state":"TX"},"items":[{"coupon":"NEWBED10","item_id":"M_STAN_K","item_name":"Standard King Mattress","item_revenue_in_usd":1075.5,"price_in_usd":1195.0,"quantity":1}],"traffic_source":"email","user_first_touch_timestamp":1593454417513109,"user_id":"UA000000106116176"}') AS schema
    
    2.  Use the from_json function to parse the JSON string into a struct. and display the Data 

            CREATE OR REPLACE TEMP VIEW parsed_events 
            AS SELECT json.* 
            FROM (
                SELECT from_json(value, 'STRUCT<device: STRING, ecommerce: STRUCT<purchase_revenue_in_usd: DOUBLE, total_item_quantity: BIGINT, unique_items: BIGINT>, event_name: STRING, event_previous_timestamp: BIGINT, event_timestamp: BIGINT, geo: STRUCT<city: STRING, state: STRING>, items: ARRAY<STRUCT<coupon: STRING, item_id: STRING, item_name: STRING, item_revenue_in_usd: DOUBLE, price_in_usd: DOUBLE, quantity: BIGINT>>, traffic_source: STRING, user_first_touch_timestamp: BIGINT, user_id: STRING>') AS json 
                FROM events_strings
                ) as json;

            SELECT * FROM parsed_events

    # %python version
    from pyspark.sql.functions import from_json, schema_of_json

    json_string = """
        {"device":"Linux","ecommerce":{"purchase_revenue_in_usd":1047.6,"total_item_quantity":2,"unique_items":2},"event_name":"finalize","event_previous_timestamp":1593879787820475,"event_timestamp":1593879948830076,"geo":{"city":"Huntington Park","state":"CA"},"items":[{"coupon":"NEWBED10","item_id":"M_STAN_Q","item_name":"Standard Queen Mattress","item_revenue_in_usd":940.5,"price_in_usd":1045.0,"quantity":1},{"coupon":"NEWBED10","item_id":"P_DOWN_S","item_name":"Standard Down Pillow","item_revenue_in_usd":107.10000000000001,"price_in_usd":119.0,"quantity":1}],"traffic_source":"email","user_first_touch_timestamp":1593583891412316,"user_id":"UA000000106459577"}
        """
    parsed_eventsDF = (events_stringsDF
            .select(from_json("value", schema_of_json(json_string)).alias("json"))
            .select("json.*")
        )

    display(parsed_eventsDF)

TODO:
    -- # SQL version

    -- ## Mamipulating Arrays and Structs with Explode() and Size()
    --     Spark SQL has a number of functions for manipulating array data, including the following:

    --     # explode() separates the elements of an array into multiple rows; this creates a new row for each element.

        CREATE OR REPLACE TEMP VIEW exploded_events AS
        SELECT *, explode(items) AS item
        FROM parsed_events;

        -- size() provides a count for the number of elements in an array for each row.
        SELECT * FROM exploded_events WHERE size(items) > 2

    # Python version
        from pyspark.sql.functions import explode, size

        exploded_eventsDF = (parsed_eventsDF.select("*", explode("items").alias("item"))
            )
        #OR 
        exploded_eventsDF = (parsed_eventsDF.withColumn("items", explode("item"))
            )

        # Size()
        exploded_eventsDF.where(size("items") > 2).show()

###########################################################################################
## combines array transformations to create a table that shows the unique collection
###########################################################################################

# SQL version
 SELECT user_id,
  collect_set(event_name) AS event_history,
  array_distinct(flatten(collect_set(items.item_id))) AS cart_history
    FROM exploded_events
    GROUP BY user_id

# Python version

from pyspark.sql.functions import array_distinct, collect_set, flatten

display(exploded_eventsDF
    .groupby("user_id")
    .agg(collect_set("event_name").alias("event_history"),
            array_distinct(flatten(collect_set("items.item_id"))).alias("cart_history"))
)

## Combine and Reshape Data with Joins and Pivot Tables
# SQL version
    CREATE OR REPLACE TEMP VIEW item_purchases AS

    SELECT * 
    FROM (SELECT *, explode(items) AS item FROM sales) a
    INNER JOIN item_lookup b
    ON a.item.item_id = b.item_id;

    SELECT * FROM item_purchases

# Python version
    exploded_salesDF = (spark
        .table("sales")
        .withColumn("item", explode("items"))
    )

    itemsDF = spark.table("item_lookup")

    item_purchasesDF = (exploded_salesDF
        .join(itemsDF, exploded_salesDF.item.item_id == itemsDF.item_id)
    )

    display(item_purchasesDF)


# Pivot Tables
    # SQL version
        SELECT *
        FROM item_purchases
        PIVOT (
        sum(item.quantity) FOR item_id IN (
            'P_FOAM_K',
            'M_STAN_Q',
            'P_FOAM_S',
            'M_PREM_Q',
            'M_STAN_F',
            'M_STAN_T',
            'M_PREM_K',
            'M_PREM_F',
            'M_STAN_K',
            'M_PREM_T',
            'P_DOWN_S',
            'P_DOWN_K')
        )
  
    # Python version
        transactionsDF = (item_purchasesDF
            .groupBy("order_id", 
                "email",
                "transaction_timestamp", 
                "total_item_quantity", 
                "purchase_revenue_in_usd", 
                "unique_items",
                "items",
                "item",
                "name",
                "price")
            .pivot("item_id")
            .sum("item.quantity")
        )
        display(transactionsDF)