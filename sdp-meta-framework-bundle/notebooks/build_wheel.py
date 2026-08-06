# Databricks notebook source
# =============================================================================
# Build SDP-META Wheel from Framework Source
# =============================================================================
# This notebook builds the wheel from framework/setup.py.
# Used by the wheel_build_and_deploy job when framework code changes.
# =============================================================================

import subprocess
import sys
import os
from pathlib import Path

# --- Get parameters ---
framework_path = dbutils.widgets.get("framework_path")  # noqa: F821
volume_path = dbutils.widgets.get("volume_path")  # noqa: F821

print(f"Framework path: {framework_path}")
print(f"Volume path: {volume_path}")

# --- Resolve paths ---
# In workspace context, files are accessible via /Workspace prefix
if not framework_path.startswith("/Workspace"):
    framework_path = f"/Workspace{framework_path}"

fw_path = Path(framework_path)
setup_py = fw_path / "setup.py"

if not setup_py.exists():
    raise FileNotFoundError(
        f"setup.py not found at {setup_py}. "
        f"Ensure framework/ directory contains the SDP-META source code."
    )

# --- Build the wheel ---
dist_dir = fw_path / "dist"
dist_dir.mkdir(exist_ok=True)

print(f"\nBuilding wheel from {fw_path}...")
result = subprocess.run(
    [
        sys.executable, "-m", "pip", "wheel",
        "--no-deps",
        "--no-build-isolation",
        "--wheel-dir", str(dist_dir),
        str(fw_path),
    ],
    capture_output=True,
    text=True,
)

print(result.stdout)
if result.returncode != 0:
    print(f"STDERR: {result.stderr}")
    raise RuntimeError(f"Wheel build failed with exit code {result.returncode}")

# --- Find the built wheel ---
wheels = sorted(dist_dir.glob("databricks_labs_sdp_meta-*.whl"))
if not wheels:
    raise RuntimeError(f"No wheel found in {dist_dir}")

wheel_file = wheels[-1]
print(f"\nWheel built successfully: {wheel_file.name}")
print(f"Full path: {wheel_file}")

# --- Store wheel path for next task ---
dbutils.jobs.taskValues.set(key="wheel_local_path", value=str(wheel_file))  # noqa: F821
dbutils.jobs.taskValues.set(key="wheel_filename", value=wheel_file.name)  # noqa: F821
