###########################################################################################
# First level of cleaning operations check for null values in the columns and drop them
###########################################################################################
        # SQL approach:
            SELECT count(*), count(user_id), count(user_first_touch_timestamp), count(email), count(updated)
            FROM users_dirty

            # Other Checks:

                SELECT count_if(email IS NULL) from users_dirty
                SELECT count(*) FROM users_dirty WHERE email IS NULL;

        # Spark Python API approach:
        %python 
            from pyspark.sql.functions import col
            usersDF = spark.read.table("users_dirty")

            usersDF.selectExpr("count_if(email IS NULL)")
            usersDF.where(col("email").isNull()).count()
 ###########################################################################################
 # Second level of cleaning operations check for duplicates in the columns and drop them
###########################################################################################
    # SQL approach:
    %sql
        SELECT DISTINCT (*) FROM users_dirty

    # Spark Python API approach:
    %python 
        usersDF.dropDuplicates().show()
        usersDF.distinct().display()

    ## Deduplicate Rows Based on Specific Columns

        # SQL approach:
            CREATE OR REPLACE TEMP VIEW deduped_users AS 
            SELECT user_id, user_first_touch_timestamp, max(email) AS email, max(updated) AS updated
            FROM users_dirty
            WHERE user_id IS NOT NULL
            GROUP BY user_id, user_first_touch_timestamp;

            SELECT count(*) FROM deduped_users;

        # Spark Python API approach:
         %python
            from pyspark.sql.functions import max
            dedupedDF = (usersDF
                .where(col("user_id").isNotNull())
                .groupBy("user_id", "user_first_touch_timestamp")
                .agg(max("email").alias("email"), 
                    max("updated").alias("updated"))
                )
            dedupedDF.count()
    
        ## Alternative, Solution
          %python
            dedupedDF = (usersDF
                .dropDuplicates(["user_id", "user_first_touch_timestamp"])
                .filter(col("user_id").isNotNull())
                .count())

        ## Validate the Deduplication
          %python
            from pyspark.sql.functions import count

            display(dedupedDF
                .groupBy("user_id")
                .agg(count("*").alias("row_count"))
                .select((max("row_count") <= 1).alias("no_duplicate_ids")))

        ## SQL 
          %sql
            SELECT max(row_count) <= 1 no_duplicate_ids 
                FROM (
                SELECT user_id, count(*) AS row_count
                FROM deduped_users
                GROUP BY user_id
                )
        ## Confirm that each email is associated with at most one **`user_id`**.
          %sql 
          SELECT max(user_id_count) <= 1 as at_most_one_id 
            FROM (
            SELECT email, count(user_id) AS user_id_count
            FROM deduped_users
            WHERE email IS NOT NULL
            GROUP BY email
                )

          %python
            display(dedupedDF
                .where(col("email").isNotNull())
                .groupBy("email")
                .agg(count("user_id").alias("user_id_count"))
                .select((max("user_id_count") <= 1).alias("at_most_one_id")))


# Third level of cleaning operations check for outliers in the columns and drop them
# Fourth level of cleaning operations check for invalid values in the columns and drop them
# Fifth level of cleaning operations check for inconsistent values in the columns and drop them
# Sixth level of cleaning operations check for irrelevant values in the columns and drop them
# Seventh level of cleaning operations check for irrelevant columns and drop them
# Eighth level of cleaning operations check for irrelevant rows and drop them