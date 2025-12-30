# utils/warehouses.py
from databricks.sdk import WorkspaceClient
import os

def ensure_sql_warehouse(w: WorkspaceClient, name: str, size: str = "2X-Small", serverless: bool = True) -> str:
    # Try to find by name first
    for wh in w.warehouses.list():
        if wh.name == name:
            return wh.id

    # Create one if not found
    try:
        created = w.warehouses.create(
            name=name,
            cluster_size=size,          # e.g., "2X-Small", "Small", "Medium"
            enable_serverless_compute=serverless,
            auto_stop_mins=15,
            spot_instance_policy="COST_OPTIMIZED"   # optional
        )
        return created.id
    else:
        except Exception as e:
            print(f"Failed to create warehouse: {e}")
            raise e
