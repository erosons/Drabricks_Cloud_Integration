##### Amazon Kinesis

 is not a single product, but a family of services for handling real-time data streams. It provides streaming primitives
- Messages aren’t immediately pushed to subscribers. Instead, they’re stored in shards (ordered logs), and consumers poll using iterators.

it’s partitioned log storage with real-time readers.

Consumer delivery semantics: at least once (you may need to deduplicate).

Kinesis Data Streams (KDS) → The core streaming log, closest to Kafka/pub-sub.
Kinesis Data Firehose → Fully managed, no-code sink to S3, Redshift, ES, etc.
Kinesis Data Analytics → SQL/Apache Flink processing over streams.
Kinesis Video Streams → Specialized for video/audio data ingestion.

Retention is configurable (default 24 hours, up to 7 days, or longer with extended retention) — not ephemeral like pub/sub.

#### Each shard supports:

1 MB/sec or 1,000 records/sec writes
2 MB/sec reads
When you create a Kinesis Data Stream, you pick how many shards it should have.
Records are routed to shards using a partition key (like a hash key).
Ordering is guaranteed within a shard, but not across shards.

👉 Example:
If you split a stream into Shard A and Shard B:

Records with partition key "customer-123" might always go to Shard A.

Records with partition key "customer-456" might always go to Shard B.

This way, related records stay ordered together, but the stream can scale horizontally.


##### 🔹 Step 1: Producer decides partition placement

Each record published to Kinesis has a Partition Key.

Kinesis uses a hash of the partition key to decide which shard stores that record.

Example:

Partition Key = "CustomerID:123" → goes to Shard A

Partition Key = "CustomerID:456" → goes to Shard B

This ensures ordering within that customer’s data (all events for Customer 123 stay in Shard A).

##### 🔹 Step 2: Consumer reads from multiple shards

A consumer application (e.g., Databricks Structured Streaming, Flink, Lambda, or KCL app) can read from all shards in parallel.

Each shard acts like an ordered log; consumers use ShardIterators to walk through records.

AWS KCL (Kinesis Client Library) assigns shards to consumer workers intelligently, so you don’t have to manage shard distribution manually.

🔹 Step 3: Re-organize data at the sink

Once records are pulled from different shards, you need a strategy to “re-unify” them at the sink (database, data lake, or analytics engine). Common patterns:

#####  1. Hash-based Routing (by Partition Key)

In your sink (e.g., S3, Delta Lake, DynamoDB), store records based on the same key you used in Kinesis.

Example:

All "CustomerID:123" events → S3 path …/customer=123/

All "CustomerID:456" events → S3 path …/customer=456/

This keeps related data together and ordered.

2. Time-based Batching

Organize records by event timestamp or ingestion timestamp.

Example sink partitioning:

/year=2025/month=09/day=26/hour=05/

Useful for analytics pipelines (Databricks, Athena, Redshift Spectrum).

#####  3. Composite Partitioning

Use both partition key + time window.

Example:

/customer=123/year=2025/month=09/day=26/

Balances query efficiency (by customer) and time-based roll-ups.

#####  4. Exactly-once Semantics (deduplication)

Since Kinesis guarantees at least once delivery, consumers often add:

SequenceNumber (from Kinesis) to detect duplicates.

Idempotent writes in the sink (e.g., upserts into Delta Lake / DynamoDB).

##### Create the Kinesis Data Stream

AWS Console / CLI: Create a stream (e.g., my-lab-stream) with 1–2 shards for experimentation.

Each shard can handle:

1 MB/sec (write throughput)

2 MB/sec (read throughput)

1,000 records/sec writes

For production, shard count is sized based on ingestion rate.

##### 2. Set Up Secure Access (IAM Roles & Policies)

IAM Role: Create an IAM role that grants permissions to read from/write to Kinesis.
Example policy snippet:

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kinesis:DescribeStream",
        "kinesis:GetRecords",
        "kinesis:GetShardIterator",
        "kinesis:ListStreams",
        "kinesis:PutRecord",
        "kinesis:PutRecords"
      ],
      "Resource": "arn:aws:kinesis:us-east-1:123456789012:stream/my-lab-stream"
    }
  ]
}


###### AUTHENTICATION ######
Add this line to cross account Polices that was used to create databricks line policies
- {
   "Efeect" : "Allow",
   "Action" : "iam:PassRole"
   "Resource": <"roleARN">

}

Instance Profile: Attach the IAM role to an EC2 instance profile so Databricks clusters running on EC2 can assume this role automatically.

Databricks: In workspace admin, attach the instance profile to your cluster.

##### 3. Connect Databricks to Kinesis

Databricks clusters can access AWS services using instance profiles (no explicit keys/secrets needed).

In Spark, you use the Kinesis connector for Structured Streaming
.

Example consumer in Scala:

val kinesisStreamName = "dbacademy-test-data-stream"
val kinesisRegion = "us-east-1"

val kinesis = spark.readStream
  .format("kinesis")
  .option("streamName", kinesisStreamName)
  .option("region", kinesisRegion)
  .option("initialPosition", "TRIM_HORIZON")
  .load()

kinesis.writeStream
  .format("delta")
  .option("checkpointLocation", "/tmp/kinesis-demo/_checkpoint")
  .table("main.default.kinesis_demo_bronze")


df.writeStream
  .format("console")
  .outputMode("append")
  .start()
  .awaitTermination()


Example producer in Scala:

import java.nio.ByteBuffer
import com.amazonaws.services.kinesis.AmazonKinesisClientBuilder
import com.amazonaws.services.kinesis.model.PutRecordRequest

val kinesis = AmazonKinesisClientBuilder.defaultClient()
val putReq = new PutRecordRequest()
  .withStreamName("my-lab-stream")
  .withPartitionKey("partitionKey")
  .withData(ByteBuffer.wrap("Hello Kinesis".getBytes()))

kinesis.putRecord(putReq)

##### 4. Hands-On Requirements

To follow along, you’ll need:

AWS account with admin privileges (to create streams, roles, and profiles).

Databricks workspace with the ability to attach instance profiles.

Permission to configure IAM roles and policies.

Basic familiarity with Scala/Spark Structured Streaming.