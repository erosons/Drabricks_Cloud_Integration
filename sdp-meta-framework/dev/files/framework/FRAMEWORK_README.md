# SDP-META Framework Source

This directory contains the **SDP-META framework source code** used to build the wheel.

## Directory Structure (sync from local-meta-sdp)

```
framework/
├── setup.py                    # Package build configuration
├── MANIFEST.in                 # Include templates in wheel
├── README.md                   # Package README (used in wheel metadata)
├── src/
│   └── databricks/
│       └── labs/
│           └── sdp_meta/
│               ├── __init__.py
│               ├── __about__.py        # Version info
│               ├── __main__.py         # CLI entry point
│               ├── dataflow_pipeline.py  # Core pipeline logic
│               ├── dataflow_spec.py    # Spec table schema
│               ├── bundle.py           # DAB commands
│               ├── stage_conf.py       # Conf staging to volumes
│               ├── identifiers.py      # UC name validation
│               └── templates/          # DAB template files
└── compat/
    ├── dlt_meta/                   # v0.0.10 compatibility shim
    └── src/                        # Legacy import compatibility
```

## How to Sync Framework Source

Copy the framework source from the standalone repo:

```bash
# From workspace root
cp -r local-meta-sdp/src framework/src
cp -r local-meta-sdp/compat framework/compat
cp local-meta-sdp/setup.py framework/setup.py
cp local-meta-sdp/MANIFEST.in framework/MANIFEST.in
cp local-meta-sdp/README.md framework/README.md
```

Or use a Git submodule approach (recommended for production):

```bash
# In git repo context
git submodule add <sdp-meta-repo-url> framework
```

## Wheel Build Process

The wheel is built automatically when you:
1. Run `databricks bundle deploy` (via DAB artifacts section)
2. Run the `wheel_build_and_deploy` job manually
3. Run locally: `pip wheel --no-deps --wheel-dir dist .` from this directory

## Important Notes

- **Do NOT modify framework code for use-case-specific logic** — that belongs in conf/
- Framework changes should be tested against all 9 use cases before deploying
- Version is pinned in `src/databricks/labs/sdp_meta/__about__.py`
