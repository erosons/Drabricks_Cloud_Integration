# Partition /Core Partition Calculator Impact of Partition Count on 2 Nodes × 4 Cores

    Too Few Partitions:
        If the total number of partitions is less than or equal to 8:
            Some cores might remain idle (underutilized resources).
            Example: If there are only 6 partitions, 2 cores will remain idle on your cluster.
    Too Many Partitions:
        If the partition count is too high (e.g., 1,000):
            Each core will process many small tasks, increasing scheduling overhead.
            Example: If there are 1,000 partitions, each core will process 1,000/8 = 125 tasks.
            Shuffle: This could lead to excessive shuffling if the partitions are imbalanced.

# Both configurations are complementary and can be used together to optimize Spark workloads:

    Use spark.sql.adaptive.advisoryPartitionSizeInBytes to ensure overall partitions are optimally sized.
    Use spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes to address specific issues with skewed partitions during join operations.
    spark.conf.set("spark.sql.adaptive.enabled", "true")  # Enable AQE
    spark.conf.set("spark.sql.adaptive.advisoryPartitionSizeInBytes", "67108864")  # Set general partition target size to 64 MB
    spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "268435456")  # Skewed partition threshold at 256 MB

# spark.sql.files.maxPartitionBytes

  # Operation Phase: File Reading
    Localized Operation:
        This is a localized operation because it occurs when Spark reads input files.
        The data is partitioned directly from the file system, splitting large files into smaller chunks according to the specified size.
    Impact on Shuffling:
        It does not directly cause shuffling, as this configuration only determines how files are split into partitions during the initial file scan.
        However, poorly configured partition sizes may lead to imbalanced partitions, which can later result in shuffle operations during transformations like joins or aggregations.
    Does It Cause Shuffling?
        No shuffling during file reading.
        Indirectly impacts shuffling downstream if partitions are too small or too large, as it can lead to skewed partitions.

# spark.sql.adaptive.advisoryPartitionSizeInBytes

    Operation Phase: Query Execution (with Adaptive Query Execution - AQE enabled)
    Localized or Shuffling:
        Localized: If the advisory partitioning aligns with the upstream transformations, it may avoid unnecessary data movement.
        Shuffling: If the advisory partitioning results in partition merging or repartitioning due to skew or other adjustments, this can trigger shuffle operations.
    Key Role:
        Works post-file reading and dynamically adjusts partitions during the execution phase.
        It may cause shuffle operations as Spark rearranges data across executors to optimize for performance and memory usage.

    spark.sql.adaptive.advisoryPartitionSizeInBytes:
        Can cause shuffling because AQE may repartition data during execution to meet the advisory size.
        This is expected behavior and is usually beneficial as it helps balance partition sizes dynamically.

Key Insights

    Localized:
        File splitting (spark.sql.files.maxPartitionBytes) is inherently a localized operation during the read phase.
    Shuffling:
        Advisory partition sizing (spark.sql.adaptive.advisoryPartitionSizeInBytes) occurs during query execution and may involve shuffling.
"""

# How to Choose the Right Value for spark.sql.shuffle.partitions 

    Cluster Resources:
        Example: For a cluster with 32 cores, set spark.sql.shuffle.partitions to 64–128 for balanced performance.

    Dataset Size:
        Target 64–128 MB per partition:
            Dataset size = 1 TB
            Partition size = 128 MB
            spark.sql.shuffle.partitions = (1 TB ÷ 128 MB) = ~8192

    Iterative Tuning:
        Start with 2–4x the number of cores and monitor job performance.
        Adjust based on task execution time, shuffle write/read sizes, and memory usage.


# Partition Decision 

    Target Partition Size:
        The recommended partition size for Spark is between 100MB and 1GB.
        - Smaller partitions (e.g., 100MB) are more suitable for iterative operations, 
        - while larger partitions (closer to 1GB) are efficient for sequential operations.

    Available Memory per Executor:
        Executors: Each node will run executors, and the number depends on the available cores and memory. For your cluster:
            Executors per node = 4 cores/1 core per executor=44 cores/1 core per executor=4
            Memory per executor = 16 GB/4 executors=4 GB per executor16 GB/4 executors=4 GB per executor
        The partition size should be significantly smaller than the memory per executor to avoid out-of-memory errors. 
        A safe starting point is Memory4−54−5Memory​ (e.g., 4GB/4=1GB4GB/4=1GB).

    Type of Operations:
        -> Wide transformations 
             like join and groupBy involve shuffling and are sensitive to partitioning. Partitions should be evenly distributed to avoid skew.
        -> Narrow transformations
              like map or filter operate on partitions independently and benefit from smaller partitions.

  * *** Shuffle and Storage Disk I/O: *****
        During shuffle operations, Spark writes temporary data to disk. Larger partitions reduce disk I/O during shuffle but can increase memory pressure.
        Partition size should balance memory usage and disk I/O performance.

    Configuration Parameters:
        spark.sql.files.maxPartitionBytes: Controls the maximum size of a partition when reading data. Defaults to 128MB.
        spark.sql.shuffle.partitions: Controls the number of partitions during shuffle operations. Defaults to 200.

Calculating Partition Size

    Estimate Dataset Size:
        Example: A dataset of 10GB.
        Target partitions: 10GB128MB=80 partitions128MB10GB​=80 partitions.

    Number of Executors:
        Total executors = nodes×executors per node=2×4=8nodes×executors per node=2×4=8.
        Partitions per executor = Total partitionsTotal executorsTotal executorsTotal partitions​.

    Adjust for Workload:
        If your workload involves iterative operations, use smaller partitions (e.g., 64MB).
        For batch operations, larger partitions (e.g., 256MB) can reduce overhead.

Optimal Configuration for Your Cluster

Given your cluster's configuration:

    Memory per executor: 4GB.
    Suggested partition size: 128MB to 256MB.
    Number of partitions: Adjust based on the dataset size. For example:
        For 10GB dataset: 10GB128MB≈80 partitions128MB10GB​≈80 partitions.