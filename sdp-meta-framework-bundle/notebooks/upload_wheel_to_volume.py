# Databricks notebook source
# =============================================================================
# Upload Built Wheel to UC Volume
# =============================================================================
# Copies the freshly built wheel to the UC Volume path so all pipelines
# can %pip install it. This ensures framework changes propagate immediately.
# =============================================================================

from pathlib import Path

# --- Get parameters ---
volume_wheel_path = dbutils.widgets.get("volume_wheel_path")  # noqa: F821
framework_path = dbutils.widgets.get("framework_path")  # noqa: F821

# --- Resolve the locally built wheel ---
if not framework_path.startswith("/Workspace"):
    framework_path = f"/Workspace{framework_path}"

dist_dir = Path(framework_path) / "dist"
wheels = sorted(dist_dir.glob("databricks_labs_sdp_meta-*.whl"))

if not wheels:
    raise RuntimeError(
        f"No wheel found in {dist_dir}. Run build_wheel task first."
    )

wheel_file = wheels[-1]
print(f"Source wheel: {wheel_file}")
print(f"Target volume path: {volume_wheel_path}")

# --- Ensure wheels/ directory exists on volume ---
volume_dir = str(Path(volume_wheel_path).parent)
dbutils.fs.mkdirs(volume_dir.replace("/Volumes/", "dbfs:/Volumes/"))  # noqa: F821

# --- Copy wheel to UC Volume ---
# Use dbutils.fs.cp for volume file operations
local_wheel_uri = f"file:{wheel_file}"
volume_uri = volume_wheel_path

dbutils.fs.cp(local_wheel_uri, volume_uri)  # noqa: F821

print(f"\nWheel uploaded successfully!")
print(f"  Source: {wheel_file}")
print(f"  Target: {volume_wheel_path}")
print(f"\nAll pipelines will use the new wheel on next refresh.")
