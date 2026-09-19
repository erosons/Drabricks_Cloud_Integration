#!/usr/bin/env python3
"""Upload DAB Wheel Artifact to UC Volume

Copies the DAB-built wheel artifact to UC Volume for external access.
The wheel is automatically built by Databricks Asset Bundle (DAB) on deploy.

Parameters are passed via command-line arguments:
  - source_wheel_path: DAB artifact path (from ${artifacts...})
  - target_volume_path: UC Volume destination path
"""

import sys
import shutil
from pathlib import Path

def main():
    # --- Get parameters from command line ---
    if len(sys.argv) < 3:
        raise ValueError(
            "Missing required parameters. "
            "Usage: upload_wheel_to_volume.py <source_wheel_path> <target_volume_path>"
        )

    source_wheel_path = sys.argv[1]  # DAB artifact path
    target_volume_path = sys.argv[2]  # UC Volume path

    print(f"Source (DAB artifact): {source_wheel_path}")
    print(f"Target (UC Volume):    {target_volume_path}")

    # --- Validate source exists ---
    wheel_file = Path(source_wheel_path)
    if not wheel_file.exists():
        raise FileNotFoundError(
            f"Source wheel not found: {source_wheel_path}\n"
            f"DAB artifact should be built automatically on bundle deploy."
        )

    print(f"\nSource wheel size: {wheel_file.stat().st_size} bytes")

    # --- Ensure target directory exists ---
    target_wheel = Path(target_volume_path)
    target_dir = target_wheel.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ensured target directory exists: {target_dir}")

    # --- Copy wheel to UC Volume ---
    # UC Volumes are FUSE-mounted, so standard file operations work
    print(f"\nCopying wheel...")
    shutil.copy2(wheel_file, target_wheel)

    # --- Verify the copy ---
    if target_wheel.exists():
        target_size = target_wheel.stat().st_size
        source_size = wheel_file.stat().st_size

        print(f"\n✓ Copy successful!")
        print(f"  Source: {source_wheel_path} ({source_size} bytes)")
        print(f"  Target: {target_volume_path} ({target_size} bytes)")

        if source_size != target_size:
            raise RuntimeError(
                f"Size mismatch! Source: {source_size}, Target: {target_size}"
            )
    else:
        raise RuntimeError(
            f"Copy verification failed: {target_volume_path} not found after copy"
        )

    print(f"\nWheel available at UC Volume for external access.")
    print(f"Pipelines use artifact directly: {source_wheel_path}")

if __name__ == "__main__":
    main()
