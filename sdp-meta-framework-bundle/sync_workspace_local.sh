#!/bin/bash
# Run this on your LOCAL machine (not in Databricks)
# Requires: pip install databricks-cli

set -e

WORKSPACE_PATH="/Workspace/Users/samson.eromonsei@databricks.com/sdp-meta-framework-bundle"
LOCAL_DIR="/Users/samson.eromonsei/sdp-meta-framework"

echo "📥 Downloading workspace folder to local machine..."
echo "   Source:  $WORKSPACE_PATH"
echo "   Target:  $LOCAL_DIR"

mkdir -p "$LOCAL_DIR"
databricks workspace export-dir "$WORKSPACE_PATH" "$LOCAL_DIR" --overwrite --profile e2-demo-field-eng

echo "✅ Done! Files saved to $LOCAL_DIR"
echo ""
echo "To push changes back:"
echo ""