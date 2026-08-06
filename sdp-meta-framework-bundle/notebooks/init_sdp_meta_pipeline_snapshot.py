# Databricks notebook source
# =============================================================================
# SDP-META Pipeline Runner (Snapshot)
# =============================================================================
# Special runner for UC4 snapshot use case. Provides next_snapshot callbacks
# that the framework uses to manage versioned snapshot ingestion.
# =============================================================================

import dlt  # noqa: F401 - required for DLT pipeline context

# --- Install the SDP-META wheel from UC Volume ---
sdp_meta_whl = spark.conf.get("sdp_meta_whl")
exec(f"import subprocess; subprocess.check_call(['pip', 'install', '{sdp_meta_whl}'])")

# --- Import framework ---
from databricks.labs.sdp_meta.dataflow_pipeline import DataflowPipeline

layer = spark.conf.get("layer")


# --- Snapshot callback functions ---
def bronze_next_snapshot_and_version(snapshot_path, latest_version):
    """Return next snapshot file path and version for bronze layer."""
    next_version = latest_version + 1 if latest_version else 1
    next_path = f"{snapshot_path}/v{next_version}"
    try:
        dbutils.fs.ls(next_path)  # noqa: F821
        return next_path, next_version
    except Exception:
        return None, latest_version


def silver_next_snapshot_and_version(snapshot_path, latest_version):
    """Return next snapshot file path and version for silver layer."""
    return bronze_next_snapshot_and_version(snapshot_path, latest_version)


# --- Invoke with callbacks ---
DataflowPipeline.invoke_dlt_pipeline(
    spark,
    layer,
    bronze_next_snapshot_and_version=bronze_next_snapshot_and_version,
    silver_next_snapshot_and_version=silver_next_snapshot_and_version,
)
