#!/bin/bash
# Run this on your LOCAL machine (not in Databricks)
# Requires: pip install databricks-cli
databricks auth login --profile fevm-machine
set -e

WORKSPACE_PATH="/Workspace/deployment/.bundle/sdp-meta-framework"
LOCAL_DIR="/Users/samson.eromonsei/sp-framework/sdp-meta-framework"

echo "📥 Downloading workspace folder to local machine..."
echo "   Source:  $WORKSPACE_PATH"
echo "   Target:  $LOCAL_DIR"

mkdir -p "$LOCAL_DIR"
databricks workspace export-dir "$WORKSPACE_PATH" "$LOCAL_DIR" --overwrite --profile fevm-machine

echo "✅ Done! Files saved to $LOCAL_DIR"
echo ""
echo "To push changes back:"
echo ""