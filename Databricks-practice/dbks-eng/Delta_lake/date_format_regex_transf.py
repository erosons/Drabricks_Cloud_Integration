## SQL
    # %sql
    SELECT *, 
    date_format(first_touch, "MMM d, yyyy") AS first_touch_date,
    date_format(first_touch, "HH:mm:ss") AS first_touch_time,
    regexp_extract(email, "(?<=@).+", 0) AS email_domain
    FROM (
    SELECT *,
        CAST(user_first_touch_timestamp / 1e6 AS timestamp) AS first_touch 
    FROM deduped_users
    )

## Python
    # %python
    from pyspark.sql.functions import date_format, regexp_extract
    dedupedDF = (dedupedDF
        .withColumn("first_touch", (col("user_first_touch_timestamp")/1e6).cast("timestamp"))
        .withColumn("first_touch_date", date_format("first_touch", "MMM d, yyyy"))
        .withColumn("first_touch_time", date_format("first_touch", "HH:mm:ss"))
        .withColumn("email_domain", regexp_extract("email", "(?<=@).+", 0))
        )
    display(dedupedDF)