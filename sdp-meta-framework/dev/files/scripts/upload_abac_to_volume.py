# Upload ABAC securables to UC Volume
import sys
sys.path.insert(0, "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac/src")

# Copy securables from workspace to UC Volume
import shutil
import os

workspace_path = "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac"
volume_path = "/Volumes/general_use/platform_admin/sdp_meta_files/conf/abac"

# Create target directory if needed
os.makedirs(volume_path, exist_ok=True)

# Copy files
for filename in ["bronze_securables.yml", "silver_securables.yml"]:
    src = f"{workspace_path}/{filename}"
    dst = f"{volume_path}/{filename}"
    shutil.copy2(src, dst)
    print(f"Copied {src} -> {dst}")

print(f"\n✓ ABAC securables uploaded to UC Volume")
