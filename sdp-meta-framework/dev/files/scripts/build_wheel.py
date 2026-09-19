#!/usr/bin/env python3
"""Build SDP-META Wheel from Framework Source

This script builds the wheel from framework/setup.py (plain file).
Designed to run as a spark_python_task (file-based, not notebook).

Parameters are passed via command-line arguments:
  - framework_path: Path to framework directory containing setup.py
  - volume_path: UC Volume path (optional, for future use)
"""

import subprocess
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path

def main():
    # --- Get parameters from command line ---
    if len(sys.argv) < 2:
        raise ValueError(
            "Missing required parameter: framework_path. "
            "Usage: build_wheel.py <framework_path> [volume_path]"
        )

    framework_path = sys.argv[1]
    volume_path = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Framework path: {framework_path}")
    if volume_path:
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

    # Verify setup.py is a plain file (not notebook)
    print(f"\nVerified setup.py exists at: {setup_py}")

    # --- Copy framework to /tmp for building ---
    # /Workspace files are in special format - copy to /tmp first
    temp_dir = Path(tempfile.mkdtemp(prefix="sdp_meta_build_"))
    temp_fw_path = temp_dir / "framework"

    print(f"\nCopying framework to temporary location for building...")
    print(f"  Source: {fw_path}")
    print(f"  Temp: {temp_fw_path}")

    shutil.copytree(fw_path, temp_fw_path, symlinks=False, ignore_dirs_exist_ok=False)
    print(f"  Copied successfully")

    # --- Build the wheel from temp location ---
    dist_dir = temp_fw_path / "dist"
    dist_dir.mkdir(exist_ok=True)

    print(f"\nBuilding wheel from {temp_fw_path}...")
    result = subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir", str(dist_dir),
            str(temp_fw_path),
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

    # --- Copy wheel back to original framework location ---
    # The next task needs to find it in the workspace location
    workspace_dist = fw_path / "dist"
    workspace_dist.mkdir(exist_ok=True)

    workspace_wheel = workspace_dist / wheel_file.name
    shutil.copy2(wheel_file, workspace_wheel)
    print(f"Copied wheel to workspace: {workspace_wheel}")

    # --- Output wheel info for next task ---
    # Write to a JSON file that the next task can read
    output_file = fw_path / "wheel_build_output.json"
    output_data = {
        "wheel_local_path": str(workspace_wheel),
        "wheel_filename": wheel_file.name,
        "build_status": "success"
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nOutput written to: {output_file}")
    print(json.dumps(output_data, indent=2))

    # --- Cleanup temp directory ---
    print(f"\nCleaning up temporary directory: {temp_dir}")
    shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
