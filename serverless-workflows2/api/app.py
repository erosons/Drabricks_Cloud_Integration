# api/app.py
from flask import Flask, request, jsonify
from databricks.sdk import WorkspaceClient
import os, json, pathlib, yaml
from pyspark.sql import SparkSession


app = Flask(__name__)
w = WorkspaceClient(  # requires env vars: DATABRICKS_HOST, DATABRICKS_TOKEN
    host=os.environ["DATABRICKS_HOST"],
    token=os.environ["DATABRICKS_TOKEN"]
)
spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

#financial services domain
domain = os.environ["DATABRICKS_DOMAIN"] or "cards_services"
warehouse_id = os.getenv("warehouse_id",None)  # severlesscompute

# REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
current_user = spark.sql("SELECT current_user()").collect()[0][0]
BASE_PATH = f"/Workspace/Users/{current_user}"



# help function for parameters mapping 
def load_workflow_params() -> dict:
    workflow_path=pathlib.Path(f"{BASE_PATH}/severless_workflow/workflows/workflows.json")
    if not_path.exists():
       return jsonify({"error": "workflow.json missing"}), 404
    wf = json.loads(workflow_path.read_text())
    return wf

domain = {p["name"]: p.get("default") for p in load_workflow_params().get("parameters", [])}["domain"]


@app.post(f"/pipelines/{domain}")
def upsert_pipeline(domain):
    """
    Create or update a DLT pipeline by loading the pipeline.yml as a base layer,
    then merging runtime parameters (ingest_path, catalog, schema).
    """
    # ----------- LOAD LAYER: pipeline.yml as dict -----------
    yaml_path = pathlib.Path(f"{BASE_PATH}/severless_workflow/domains/{domain}/dlt/pipeline.yml")
    if not yaml_path.exists():
        return jsonify({"error": f"Missing pipeline.yml for domain {domain}"}), 404

    with open(yaml_path, "r") as f:
        pipeline_def = yaml.safe_load(f)

    # ----------- MERGE RUNTIME CONFIG -----------
    params =load_workflow_params()
    runtime_cfg = {p["name"]: p.get("default") for p in params.get("parameters", [])}
    if not runtime_cfg and not isinstance(runtime_cfg, dict):
        return jsonify({"error": "Missing runtime configuration"}), 404

    pipeline_def["configuration"] = {
        **pipeline_def.get("configuration", {}),
        **runtime_cfg
    }

    # Build proper notebook library path
    notebook_path = f"{BASE_PATH}/severless_workflow/domains/{domain}/dlt/tables.py"
    pipeline_def["libraries"] = [{"notebook": {"path": notebook_path}}]
    pipeline_def["storage"] = f"/Volumes/{runtime_cfg['target_catalog']}/{runtime_cfg['target_schema']}/_pipelines/dlt_{domain}"

    # ----------- UPSERT PIPELINE -----------
    existing = [p for p in w.pipelines.list_pipelines() if p.name == pipeline_def["name"]]
    if existing:
        pid = existing[0].pipeline_id
        w.pipelines.edit(pipeline_id=pid, **pipeline_def)
        return jsonify({"status": "updated", "pipeline_id": pid, "name": pipeline_def["name"]})
    else:
        created = w.pipelines.create(**pipeline_def)
        return jsonify({"status": "created", "pipeline_id": created.pipeline_id, "name": pipeline_def["name"]})


@app.post(f"/jobs/{domain}")
def upsert_job(domain):
    """
    Create or update a Databricks multi-task Workflow (job) from workflow.json.
    """
    # workflow_path = REPO_ROOT / "workflows" / "workflow.json"
    # if not workflow_path.exists():
    #     return jsonify({"error": "workflow.json missing"}), 404

    # with open(workflow_path, "r") as f:
    #     job_def = json.load(f)
    job_def = load_workflow_params()

    job_def["name"] = f"job_{domain}_pipeline"

    if not warehouse_id:
        raise Exception("Missing warehouse_id")
        # create/find a default per-domain warehouse if none was supplied
    warehouse_id = ensure_sql_warehouse(w, name=f"wh-{domain}-serverless", size="2X-Small", serverless=True)

    # Inject pipeline_id and warehouse_id
    if not request.json["pipeline_id"]:
        raise Exception("Missing pipeline_id")
    for t in job_def["tasks"]:
        if "pipeline_task" in t:
            t["pipeline_task"]["pipeline_id"] = request.json["pipeline_id"]
        if "sql_task" in t:
            t["sql_task"]["warehouse_id"] = warehouse_id

    # ----------- UPSERT JOB -----------
    jobs = w.jobs.list(name=job_def["name"])
    if jobs:
        w.jobs.reset(job_id=jobs[0].job_id, new_settings=job_def)
        return jsonify({"status": "updated", "job_id": jobs[0].job_id, "name": job_def["name"]})
    else:
        created = w.jobs.create(**job_def)
        return jsonify({"status": "created", "job_id": created.job_id, "name": job_def["name"]})


if __name__ == "__main__":
    # Required ENV:
    # DATABRICKS_HOST, DATABRICKS_TOKEN, WORKSPACE_REPO
    app.run(host="0.0.0.0", port=8080, debug=True)
