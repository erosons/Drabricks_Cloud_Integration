from pyspark.sql.functions import broadcast

sample_table =''
large_table =''

# Broadcast the smaller table
optimized_join = large_table.join(broadcast(sample_table), "join_key", "inner")

# When to Use:

#     The smaller table is small enough to fit in memory on each executor (typically < 2GB).

# Benefits:

#     Eliminates shuffle of the large table.
#     Reduces network and disk I/O.


#TODO 
# Filter large table using keys from the sample table
filtered_large_table = large_table.filter(large_table["join_key"].isin(sample_table.select("join_key").distinct().collect()))

# Perform the join
optimized_join = filtered_large_table.join(sample_table, "join_key", "inner")

# When to Use:

#     Both tables are already large, and shuffling is expensive.

# Benefits:

#     Reduces shuffle and improves performance.


# TODO 

# co-partitioning (Avoid Shuffle)

# Ensure that both tables are partitioned on the same key to avoid shuffling during the join.

# Repartition both tables on the join key
large_table = large_table.repartition("join_key")
sample_table = sample_table.repartition("join_key")

# Perform the join
optimized_join = large_table.join(sample_table, "join_key", "inner")
