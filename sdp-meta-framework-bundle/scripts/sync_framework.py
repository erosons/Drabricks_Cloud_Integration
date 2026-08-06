# Databricks notebook source
# =============================================================================
# Sync Framework Source into Bundle
# =============================================================================
# This script copies the SDP-META framework source code from the standalone
# repo (local-meta-sdp) into the framework/ directory of this bundle.
#
# Run this once during initial setup, or whenever the framework source
# is updated in the standalone repo.
#
# Usage: Run as a notebook or via `databricks bundle run sync_framework`
# =============================================================================

import os
import shutil
from pathlib import Path
from io import BytesIO
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ObjectType, ExportFormat, ImportFormat

# --- Configuration ---
SOURCE_REPO_PATH = "/Workspace/Users/samson.eromonsei@databricks.com/dlt-meta-local"
TARGET_FRAMEWORK_PATH = "/Workspace/Users/samson.eromonsei@databricks.com/sdp-meta-framework-bundle/framework"

# Key directories/files to sync
SYNC_ITEMS = [
    "src",           # Main framework source (databricks.labs.sdp_meta)
    "compat",        # Backward compatibility shims
    "setup.py",      # Wheel build config
    "MANIFEST.in",   # Include non-Python files in wheel
    "README.md",     # Package README
]

w = WorkspaceClient()


# Template dirs with Go template syntax that the workspace API cannot handle
SKIP_PATTERNS = ["{{", "}}", ".tmpl"]


def should_skip(path: str) -> bool:
    """Skip files with Go template syntax in path (not needed for wheel build)."""
    return any(p in path for p in SKIP_PATTERNS)


def ensure_parent_dir(path: str):
    """Create parent directories for a target path if they don't exist."""
    parent = "/".join(path.split("/")[:-1])
    try:
        w.workspace.mkdirs(parent)
    except Exception:
        pass  # Already exists or intermediate dirs created


def delete_if_exists(path: str):
    """Delete a workspace object if it exists (handles type conflicts)."""
    try:
        w.workspace.delete(path)
    except Exception:
        pass


def sync_workspace_file(src_path: str, dst_path: str):
    """Sync a single workspace file using the appropriate API based on object type."""
    if should_skip(src_path):
        return  # Skip template files silently
    ensure_parent_dir(dst_path)

    # Check source type to pick the right API
    info = w.workspace.get_status(src_path)
    obj_type = str(info.object_type) if info.object_type else ""

    if "NOTEBOOK" in obj_type:
        # Source is stored as a notebook -> export as SOURCE, import as AUTO
        # Delete target first to avoid type mismatch if it exists as FILE
        resp = w.workspace.export(src_path, format=ExportFormat.SOURCE)
        delete_if_exists(dst_path)
        w.workspace.import_(
            path=dst_path,
            content=resp.content,
            format=ImportFormat.AUTO,
            overwrite=True,
        )
    else:
        # Source is a regular file -> download/upload raw bytes
        # Delete target first in case of type mismatch
        try:
            with w.workspace.download(src_path) as f:
                content = f.read()
            if not content:
                raise ValueError("Empty content")
            delete_if_exists(dst_path)
            w.workspace.upload(dst_path, BytesIO(content), overwrite=True)
        except Exception:
            # Fallback: try export as SOURCE for files misclassified as notebooks
            resp = w.workspace.export(src_path, format=ExportFormat.SOURCE)
            delete_if_exists(dst_path)
            w.workspace.import_(
                path=dst_path,
                content=resp.content,
                format=ImportFormat.AUTO,
                overwrite=True,
            )


def sync_workspace_dir(src_path: str, dst_path: str):
    """Recursively sync a workspace directory."""
    try:
        items = list(w.workspace.list(src_path))
    except Exception as e:
        print(f"  ⚠ Cannot list {src_path}: {e}")
        return

    for item in items:
        item_name = item.path.split('/')[-1]
        src_item = f"{src_path}/{item_name}"
        dst_item = f"{dst_path}/{item_name}"

        if item.object_type in (ObjectType.DIRECTORY, "DIRECTORY"):
            sync_workspace_dir(src_item, dst_item)
        else:
            try:
                sync_workspace_file(src_item, dst_item)
            except Exception as e:
                print(f"  ⚠ Failed to sync {src_item}: {e}")


print("="*60)
print("SDP-META Framework Sync")
print("="*60)
print(f"Source: {SOURCE_REPO_PATH}")
print(f"Target: {TARGET_FRAMEWORK_PATH}")
print()

for item in SYNC_ITEMS:
    src = f"{SOURCE_REPO_PATH}/{item}"
    dst = f"{TARGET_FRAMEWORK_PATH}/{item}"
    print(f"Syncing: {item}")
    try:
        info = w.workspace.get_status(src)
        if info.object_type in (ObjectType.DIRECTORY, "DIRECTORY"):
            sync_workspace_dir(src, dst)
            print(f"  ✓ Directory synced")
        else:
            sync_workspace_file(src, dst)
            print(f"  ✓ File synced")
    except Exception as e:
        print(f"  ✗ Error: {e}")

print()
print("✅ Framework sync complete!")
print("   Next: Run 'databricks bundle deploy' to build wheel and deploy.")
