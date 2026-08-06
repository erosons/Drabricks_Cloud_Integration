# Databricks Asset Bundle (DABs) Template

A standardized template for deploying workloads to Databricks through the centralized CI/CD orchestrator.

## Quick Start

### 1. Clone This Template

```bash
# Clone or copy this template to your new repository
git clone https://github.com/org/dabs-template.git my-workload
cd my-workload
rm -rf .git
git init
```

### 2. Configure Your Project

Update `databricks.yml`:

```yaml
bundle:
  name: my-workload  # Change to your project name

variables:
  project_name:
    default: "my-workload"  # Match bundle name
  
  notification_email:
    default: "your-team@company.com"  # Your team email
```

### 3. Update Target Workspaces

In `databricks.yml`, update the workspace hosts for each environment:

```yaml
targets:
  dev:
    workspace:
      host: https://adb-xxxx.azuredatabricks.net  # Your DEV workspace
  qa:
    workspace:
      host: https://adb-yyyy.azuredatabricks.net  # Your QA workspace
  # ... etc
```

### 4. Add GitHub Secrets

Add these secrets to your repository (Settings → Secrets → Actions):

| Secret | Description |
|--------|-------------|
| `ORCHESTRATOR_APP_ID` | GitHub App ID for orchestrator communication |
| `ORCHESTRATOR_APP_PRIVATE_KEY` | GitHub App private key |

### 5. Push and Deploy

```bash
git add .
git commit -m "Initial commit"
git push -u origin main
```

The GitHub Actions workflow will automatically trigger deployment to DEV.

---

## Project Structure

```
├── databricks.yml              # Main DABs configuration
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD workflow
├── src/
│   ├── notebooks/              # Databricks notebooks
│   │   ├── bronze_ingestion.py
│   │   ├── silver_transform.py
│   │   ├── gold_aggregate.py
│   │   └── data_quality_checks.py
│   ├── pipelines/              # DLT pipeline definitions
│   ├── jobs/                   # Additional job definitions
│   └── tests/                  # Unit tests
├── resources/                  # Additional resource configs
├── fixtures/                   # Test fixtures
└── docs/                       # Documentation
```

---

## Medallion Architecture

This template follows the medallion (bronze/silver/gold) architecture:

### Bronze Layer
- **Purpose:** Raw data ingestion
- **Pattern:** Append-only with metadata
- **Notebook:** `bronze_ingestion.py`

### Silver Layer
- **Purpose:** Cleansed, conformed data
- **Pattern:** Merge/upsert with deduplication
- **Notebook:** `silver_transform.py`

### Gold Layer
- **Purpose:** Business aggregations
- **Pattern:** Overwrite with computed metrics
- **Notebook:** `gold_aggregate.py`

---

## Environment Promotion

Deployments follow a sequential promotion path:

```
DEV → QA → UAT → PROD
```

### Trigger Conditions

| Environment | Trigger |
|-------------|---------|
| DEV | Push to `main` branch |
| QA | Push to `release/*` branch |
| UAT | After successful QA deployment |
| PROD | Git tag `v*` (requires approval) |

### Manual Deployment

Use the GitHub Actions "Run workflow" button to manually deploy to any environment.

---

## Configuration Reference

### Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `project_name` | Project identifier | `my-workload` |
| `catalog` | Unity Catalog name | `dev_catalog` |
| `schema` | Target schema | `default` |
| `warehouse_id` | SQL Warehouse ID | (empty) |
| `notification_email` | Alert email | `team@company.com` |
| `cluster_policy_id` | Cluster policy | (env-specific) |

### Environment Overrides

Each target (dev/qa/uat/prod) can override:
- Catalog and schema names
- Cluster sizes and configurations
- Job schedules
- Notification recipients

---

## Local Development

### Prerequisites

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) v0.200+
- Python 3.9+
- Azure CLI (for authentication)

### Setup

```bash
# Authenticate to Databricks
databricks auth login --host https://adb-xxxx.azuredatabricks.net

# Validate bundle
databricks bundle validate

# Deploy to dev (requires local auth)
databricks bundle deploy -t dev
```

### Run Jobs Locally

```bash
# Run a specific job
databricks bundle run main_etl_job -t dev
```

---

## Data Quality

The `data_quality_checks.py` notebook includes:

- **NOT NULL checks:** Validate required columns
- **UNIQUE checks:** Verify business keys
- **ROW COUNT checks:** Ensure data presence
- **FRESHNESS checks:** Validate data recency
- **VALUE RANGE checks:** Boundary validation
- **REFERENTIAL INTEGRITY:** Cross-table consistency

### Adding Custom Checks

```python
dq = DataQualityChecker(catalog, schema)

# Add your custom checks
dq.check_not_null("my_table", ["id", "name"])
dq.check_unique("my_table", ["id"])
dq.check_value_range("my_table", "amount", min_val=0)
```

---

## Customization Guide

### Adding a New Job

1. Create notebook in `src/notebooks/`
2. Add job definition in `databricks.yml`:

```yaml
resources:
  jobs:
    my_new_job:
      name: "${var.project_name}-my-new-job"
      tasks:
        - task_key: "task1"
          notebook_task:
            notebook_path: ./src/notebooks/my_notebook.py
```

### Adding DLT Pipeline

Uncomment the `pipelines` section in `databricks.yml` and add your DLT notebooks to `src/pipelines/`.

### Modifying Cluster Configuration

Update cluster specs in the target-specific sections:

```yaml
targets:
  prod:
    resources:
      jobs:
        main_etl_job:
          tasks:
            - task_key: "bronze_ingestion"
              new_cluster:
                num_workers: 8  # Scale for production
```

---

## Troubleshooting

### Common Issues

**Bundle validation fails:**
```bash
databricks bundle validate
# Check YAML syntax and required fields
```

**Deployment fails with OIDC error:**
- Verify Azure AD federation is configured
- Check orchestrator has correct permissions

**Job fails to start:**
- Verify cluster policy exists in target workspace
- Check Unity Catalog permissions

### Getting Help

- Databricks Support Channel (Slack)
- CI/CD Team: cicd-team@company.com
- [Internal Wiki](https://wiki.company.com/databricks)

---

## Contributing

1. Create a feature branch
2. Make changes
3. Submit PR against `main`
4. After merge, changes deploy to DEV automatically

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02 | Initial template release |
