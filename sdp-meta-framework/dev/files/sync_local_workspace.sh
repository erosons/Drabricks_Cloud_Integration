#!/bin/bash
# Run this on your LOCAL machine (not in Databricks)
# Requires: pip install databricks-cli


set -e

databricks auth login --profile fevm-machine

WORKSPACE_PATH="/Workspace/abac-mvp2"
LOCAL_DIR="/Users/samson.eromonsei/Abac"

echo "📤 Uploading local folder to workspace..."
echo "   Source:  $LOCAL_DIR"
echo "   Target:  $WORKSPACE_PATH"

databricks workspace import-dir "$LOCAL_DIR" "$WORKSPACE_PATH" --overwrite --profile fevm-machine

echo "✅ Done! Files uploaded to $WORKSPACE_PATH"
"""

print(script)
print("\n" + "="*60)
print("Copy the script above and run it in your local terminal.")
print("Make sure 'databricks' CLI is installed and authenticated.")
print("="*60)