# Databricks notebook source
# =============================================================================
# SDP-META Pipeline Runner (Standard)
# =============================================================================
# This notebook is the entry point for all non-snapshot SDP-META pipelines.
# It installs the wheel, reads pipeline config, and invokes the framework.
# =============================================================================

import dlt  # noqa: F401 - required for DLT pipeline context

# --- Install the SDP-META wheel from UC Volume ---
sdp_meta_whl = spark.conf.get("sdp_meta_whl")
exec(f"import subprocess; subprocess.check_call(['pip', 'install', '{sdp_meta_whl}'])")

# --- Import and invoke the framework ---
from databricks.labs.sdp_meta.dataflow_pipeline import DataflowPipeline

layer = spark.conf.get("layer")
DataflowPipeline.invoke_dlt_pipeline(spark, layer)
