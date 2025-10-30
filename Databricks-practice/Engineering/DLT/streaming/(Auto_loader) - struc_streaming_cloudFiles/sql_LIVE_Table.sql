CREATE OR REFRESH STREAMING TABLE orders_bronze
AS SELECT current_timestamp() processing_time, input_file_name() source_file, *
FROM cloud_files("${source}/orders", "json", map("cloudFiles.inferColumnTypes", "true"))


-- WITH DATA QUALITIES

CREATE OR REFRESH STREAMING TABLE orders_silver
(CONSTRAINT valid_date EXPECT (order_timestamp > "2021-01-01") ON VIOLATION FAIL UPDATE)
COMMENT "Append only orders with valid timestamps"
TBLPROPERTIES ("quality" = "silver")
AS SELECT timestamp(order_timestamp) AS order_timestamp, * EXCEPT (order_timestamp, source_file, _rescued_data)
FROM STREAM(LIVE.orders_bronze)


CREATE OR REFRESH LIVE TABLE orders_by_date
AS SELECT date(order_timestamp) AS order_date, count(*) AS total_daily_orders
FROM LIVE.orders_silver
GROUP BY date(order_timestamp)

-- Live Tables
-- * Always "correct", meaning their contents will match their definition after any update.
-- * Return same results as if table had just been defined for first time on all data.
-- * Should not be modified by operations external to the DLT Pipeline (you'll either get undefined answers or your change will just be undone).

-- Streaming Tables
-- * Only supports reading from "append-only" streaming sources.
-- * Only reads each input batch once, no matter what (even if joined dimensions change, or if the query definition changes, etc).
-- * Can perform operations on the table outside the managed DLT Pipeline (append data, perform GDPR, etc).constrain_aoolication.py
