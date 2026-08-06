# Change Request: AutoLoader File Notification Mode & External Location Support

## Status: PROPOSED

## Problem Statement

The SDP-META framework currently uses AutoLoader in **directory listing mode** by default. This is implicit — no `cloudFiles.useNotifications` option is set anywhere in the framework or onboarding JSON. Directory listing works for UC Volumes (the current dev setup) but becomes a limitation in production:

* **Higher latency** — directory listing polls periodically rather than reacting to file arrival events
* **Increased cloud API costs** — repeated LIST calls against large S3 prefixes with millions of files accumulate significant cost
* **Scalability ceiling** — at scale (>100K files per directory), listing becomes slow and may timeout

Production workloads typically land data on external cloud storage (`s3://`, `abfss://`, `gs://`) where **file notification mode** provides event-driven, sub-second detection of new files via cloud-native eventing (AWS SQS/SNS, Azure Event Grid).

## Current Framework Behavior

### Where AutoLoader is invoked (`pipeline_readers.py`, lines 27-49):

```python
def read_dlt_cloud_files(self) -> DataFrame:
    source_path = self.source_details["path"]
    input_df = (
        self.spark.readStream.format(self.source_format)
        .options(**self.reader_config_options)   # ← all bronze_reader_options passed here
        .schema(schema)
        .load(source_path)
    )
```

The framework passes `self.reader_config_options` (sourced from `bronze_reader_options` in the onboarding JSON) directly to Spark's AutoLoader reader. Since no `cloudFiles.useNotifications` is present, Spark defaults to **directory listing mode**.

### Current `bronze_reader_options` for UC1 (CloudFiles):

```json
"bronze_reader_options": {
    "cloudFiles.format": "csv",
    "cloudFiles.rescuedDataColumn": "_rescued_data",
    "header": "true",
    "cloudFiles.schemaEvolutionMode": "rescue"
}
```

No notification-related options exist. The `source_path_dev` points to a UC Volume (`/Volumes/...`), which only supports directory listing anyway.

## Proposed Enhancement

### New `source_notification_mode` Parameter

Add an explicit parameter to `source_details` in the onboarding JSON that controls AutoLoader's file discovery strategy:

```json
"source_details": {
    "source_path_dev": "{uc_volume_path}/test_data/uc1_cloudfiles/orders",
    "source_path_prod": "s3://prod-landing-bucket/orders/",
    "source_notification_mode": "file_notification",
    "source_schema_path": "{uc_volume_path}/conf/ddl/orders.ddl"
}
```

| Parameter Value | AutoLoader Behavior | Source Path Requirement |
| --- | --- | --- |
| `"directory_listing"` (default) | Polls for new files on a schedule | Works on UC Volumes AND external paths |
| `"file_notification"` | Event-driven via cloud notifications | External Location required (s3://, abfss://, gs://) |

### Framework Code Change (in `dataflow_pipeline.py`)

Add notification mode resolution before passing options to `PipelineReaders`:

```python
# In the method that builds reader_config_options before calling PipelineReaders
notification_mode = source_details.get("source_notification_mode", "directory_listing")

if notification_mode == "file_notification":
    reader_config_options["cloudFiles.useNotifications"] = "true"
    # Validate required options for notification mode
    if "cloudFiles.region" not in reader_config_options:
        logger.warning(
            f"cloudFiles.region not set for file_notification mode on "
            f"dataFlowId={dataflow_spec.dataFlowId}. Auto-detection may fail."
        )
elif notification_mode == "directory_listing":
    reader_config_options["cloudFiles.useNotifications"] = "false"
else:
    raise ValueError(
        f"Invalid source_notification_mode '{notification_mode}' for "
        f"dataFlowId={dataflow_spec.dataFlowId}. "
        f"Must be 'directory_listing' or 'file_notification'."
    )
```

### Onboarding Validation (in `onboard_dataflowspec.py`)

Add validation during onboarding to catch misconfigurations early:

```python
# Validate notification mode against source path
notification_mode = source_details.get("source_notification_mode", "directory_listing")
source_path = source_details.get(resolve_env_key("source_path", env), "")

if notification_mode == "file_notification":
    if source_path.startswith("/Volumes"):
        raise ValueError(
            f"data_flow_id={flow['data_flow_id']}: file_notification mode is not "
            f"supported for UC Volume paths. Use an external location "
            f"(s3://, abfss://, gs://) or switch to directory_listing."
        )
    if "cloudFiles.region" not in bronze_reader_options:
        logger.warning(
            f"data_flow_id={flow['data_flow_id']}: cloudFiles.region recommended "
            f"for file_notification mode to avoid auto-detection overhead."
        )
```

## External Location & Permissions (AWS)

### Prerequisites for File Notification Mode on AWS

#### 1. Unity Catalog External Location

An External Location maps a cloud storage path to Unity Catalog governance:

```sql
CREATE EXTERNAL LOCATION prod_landing_orders
  URL 's3://prod-landing-bucket/orders/'
  WITH (STORAGE CREDENTIAL prod_landing_credential)
  COMMENT 'Landing zone for order CSV files';

-- Grant the pipeline service principal read access
GRANT READ FILES ON EXTERNAL LOCATION prod_landing_orders
  TO `sdp_meta_pipeline_sp`;
```

#### 2. Storage Credential IAM Policy (AWS)

The IAM role backing the storage credential needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ReadAccess",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::prod-landing-bucket",
        "arn:aws:s3:::prod-landing-bucket/orders/*"
      ]
    },
    {
      "Sid": "S3NotificationSetup",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketNotificationConfiguration",
        "s3:PutBucketNotificationConfiguration"
      ],
      "Resource": "arn:aws:s3:::prod-landing-bucket"
    },
    {
      "Sid": "SQSAccess",
      "Effect": "Allow",
      "Action": [
        "sqs:CreateQueue",
        "sqs:DeleteQueue",
        "sqs:GetQueueUrl",
        "sqs:GetQueueAttributes",
        "sqs:SetQueueAttributes",
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:PurgeQueue"
      ],
      "Resource": "arn:aws:sqs:us-east-1:*:databricks-auto-ingest-*"
    },
    {
      "Sid": "SNSAccess",
      "Effect": "Allow",
      "Action": [
        "sns:CreateTopic",
        "sns:DeleteTopic",
        "sns:Subscribe",
        "sns:Unsubscribe",
        "sns:GetTopicAttributes",
        "sns:SetTopicAttributes",
        "sns:ListSubscriptionsByTopic"
      ],
      "Resource": "arn:aws:sns:us-east-1:*:databricks-auto-ingest-*"
    }
  ]
}
```

#### 3. AutoLoader Options for File Notification (AWS)

| Option | Required | Purpose |
| --- | --- | --- |
| `cloudFiles.useNotifications` | Yes | Enables file notification mode |
| `cloudFiles.region` | Recommended | AWS region for SQS/SNS resource creation |
| `cloudFiles.queueUrl` | Optional | Use existing SQS queue instead of auto-creating |
| `cloudFiles.useIncrementalListing` | Optional | Fallback: incremental listing (faster than full listing, no cloud infra needed) |

### Azure Equivalent (for reference)

| Permission | Role | Purpose |
| --- | --- | --- |
| Event Grid Contributor | On the storage account resource group | Create Event Grid subscription for blob events |
| Storage Blob Data Contributor | On the container | Read blob files |
| Storage Queue Data Contributor | On the storage account | Read/write the notification queue |

```json
"bronze_reader_options": {
    "cloudFiles.format": "csv",
    "cloudFiles.useNotifications": "true",
    "cloudFiles.resourceGroup": "rg-data-platform",
    "cloudFiles.subscriptionId": "<azure-subscription-id>",
    "cloudFiles.tenantId": "<azure-tenant-id>"
}
```

## Impact Assessment

### Framework Changes Required

| Component | Change | Effort |
| --- | --- | --- |
| `dataflow_pipeline.py` | Add notification mode resolution before reader invocation | Low |
| `onboard_dataflowspec.py` | Add validation for notification mode vs. source path type | Low |
| `dataflow_spec.py` | No change — `source_notification_mode` lives in `source_details` (already a map) | None |
| `pipeline_readers.py` | No change — already passes all options through | None |
| `variables.yml` | Add `source_path_prod` variable for external location paths | Low |
| `onboarding_all_usecases.json` | Add `source_notification_mode` and `source_path_prod` to relevant flows | Low |
| Documentation | Document permissions model, mode selection criteria | Medium |

### No-Change Components

`pipeline_readers.py` requires **zero code changes** because it already unpacks all reader options via `.options(**self.reader_config_options)`. Any valid Spark AutoLoader option added to `bronze_reader_options` flows through automatically.

## Decision Matrix: When to Use Each Mode

| Criteria | Directory Listing | Incremental Listing | File Notification |
| --- | --- | --- | --- |
| Source path type | UC Volume or external | External only | External only |
| Latency | Minutes (poll interval) | Minutes (faster LIST) | Seconds (event-driven) |
| Cloud IAM complexity | None (UC handles it) | Same as listing | High (SQS/SNS/EventGrid) |
| Cost at scale | High (LIST API calls) | Medium | Low (event per file) |
| Max files per directory | ~100K practical limit | ~1M | Unlimited |
| Recommended for | Dev, small datasets | Medium datasets | Production at scale |

## Migration Path: Dev → Production

```
Dev (current):                          Production (proposed):
┌─────────────────────────┐             ┌─────────────────────────────────────┐
│ source_path_dev:        │             │ source_path_prod:                   │
│   /Volumes/.../orders   │             │   s3://prod-bucket/landing/orders/  │
│                         │             │                                     │
│ notification_mode:      │             │ notification_mode:                  │
│   directory_listing     │             │   file_notification                 │
│   (implicit default)    │             │   (explicit)                        │
│                         │             │                                     │
│ Permissions:            │             │ Permissions:                        │
│   READ VOLUME only      │             │   External Location + IAM role      │
│                         │             │   with S3 + SQS + SNS access        │
└─────────────────────────┘             └─────────────────────────────────────┘
```

The `env` variable (`dev`/`prod`) in `variables.yml` determines which path is resolved at deploy time. A target override in `databricks.yml` can switch notification mode per environment:

```yaml
targets:
  dev:
    variables:
      env: dev
      # directory_listing is default — no override needed

  prod:
    variables:
      env: prod
      # Pipelines resolve source_path_prod automatically via {env} token
```

## Next Steps

- [ ] Implement `source_notification_mode` resolution in `dataflow_pipeline.py`
- [ ] Add onboarding validation for mode vs. path type
- [ ] Create External Location in Unity Catalog for production S3 paths
- [ ] Configure IAM role with SQS/SNS permissions on the storage credential
- [ ] Add `source_path_prod` to UC1 onboarding entry as a prototype
- [ ] Test file notification mode end-to-end with a single pipeline
- [ ] Document the permissions model in `sdp_meta_framework_bundle_documentation.md`

## Appendix: Incremental Listing as a Middle Ground

If file notification is too complex to set up initially, AutoLoader also supports `cloudFiles.useIncrementalListing = "true"` — a faster version of directory listing that tracks the last-seen file and only lists files after it (lexicographic order). This avoids cloud notification infrastructure while still improving performance over full listing:

```json
"bronze_reader_options": {
    "cloudFiles.format": "csv",
    "cloudFiles.useIncrementalListing": "auto",
    "cloudFiles.rescuedDataColumn": "_rescued_data"
}
```

This works on external locations without any SQS/SNS/Event Grid setup, making it a good intermediate step between dev (Volumes + full listing) and production (external + file notification).

---

*Proposed by: Genie Code | Date: 2025*
*Related: pipeline_readers.py (lines 27-49), UC1 cloudFiles, variables.yml*
*Cloud: AWS (primary), Azure (secondary reference)*
