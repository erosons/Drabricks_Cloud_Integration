"""
ABAC MVP2 — Scalable Config Loader

Globs configs/securables/**/*.yaml, merges with policies.yaml,
resolves templates, and produces a unified governance manifest
ready for the execution pipeline.

Designed to handle 2000+ table definitions efficiently.
"""

import os
import re
import glob
import yaml
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("abac_mvp2.config_loader")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ResolvedTable:
    """A fully resolved table config after template expansion."""
    table_id: str
    catalog: str
    schema: str
    description: str
    template: Optional[str]
    policy_bindings: List[str]
    inherited_policy_bindings: List[str]
    grants: List[Dict[str, Any]]
    columns: List[Dict[str, Any]]
    column_overrides: List[Dict[str, Any]]
    source_file: str


@dataclass
class GovernanceManifest:
    """The fully resolved governance manifest."""
    policies: Dict[str, Any]
    catalogs: List[Dict[str, Any]]
    schemas: List[Dict[str, Any]]
    tables: List[ResolvedTable]
    templates: Dict[str, Any]
    auto_discover_rules: List[Dict[str, Any]]
    controls: Dict[str, Any]
    stats: Dict[str, int] = field(default_factory=dict)


# =============================================================================
# CONFIG LOADER
# =============================================================================

class ABACConfigLoader:
    """
    Loads and merges multi-file ABAC configuration.
    
    Directory layout expected:
        configs/
        ├── policies.yaml
        └── securables/
            ├── _templates.yaml
            ├── _defaults.yaml
            ├── customer/
            │   ├── customer_profile.yaml
            │   └── customer_addresses.yaml
            ├── finance/
            │   └── transactions.yaml
            └── ...
    """

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.policies_path = os.path.join(config_path, "policies.yaml")
        self.securables_path = os.path.join(config_path, "securables")
        self._templates: Dict[str, Any] = {}
        self._defaults: Dict[str, Any] = {}
        self._policies: Dict[str, Any] = {}
        self._tables: List[ResolvedTable] = []

    def load(self) -> GovernanceManifest:
        """Load all configs and return a unified GovernanceManifest."""
        logger.info(f"Loading ABAC config from: {self.config_path}")

        # 1. Load policies (single file)
        self._policies = self._load_yaml(self.policies_path)
        logger.info(f"Loaded policies: {len(self._policies.get('policies', {}).get('row_filters', []))} row filters, "
                    f"{len(self._policies.get('policies', {}).get('column_masks', []))} column masks")

        # 2. Load templates
        templates_path = os.path.join(self.securables_path, "_templates.yaml")
        if os.path.exists(templates_path):
            templates_raw = self._load_yaml(templates_path)
            self._templates = templates_raw.get("templates", {})
            logger.info(f"Loaded {len(self._templates)} templates")

        # 3. Load defaults (catalogs, schemas, auto-discover rules)
        defaults_path = os.path.join(self.securables_path, "_defaults.yaml")
        if os.path.exists(defaults_path):
            self._defaults = self._load_yaml(defaults_path)
            logger.info(f"Loaded defaults: {len(self._defaults.get('catalogs', []))} catalogs, "
                        f"{len(self._defaults.get('schemas', []))} schemas")

        # 4. Glob all table config files (skip _ prefixed files)
        table_files = self._discover_table_files()
        logger.info(f"Discovered {len(table_files)} table config files")

        # 5. Load and resolve all table configs (parallel for speed)
        self._tables = self._load_tables_parallel(table_files)
        logger.info(f"Resolved {len(self._tables)} table configurations")

        # 6. Build manifest
        manifest = GovernanceManifest(
            policies=self._policies,
            catalogs=self._defaults.get("catalogs", []),
            schemas=self._defaults.get("schemas", []),
            tables=self._tables,
            templates=self._templates,
            auto_discover_rules=self._defaults.get("auto_discover", []),
            controls=self._policies.get("controls", {}),
            stats={
                "total_tables": len(self._tables),
                "total_policies": (len(self._policies.get("policies", {}).get("row_filters", []))
                                   + len(self._policies.get("policies", {}).get("column_masks", []))),
                "total_templates": len(self._templates),
                "total_schemas": len(self._defaults.get("schemas", [])),
                "total_catalogs": len(self._defaults.get("catalogs", [])),
            }
        )
        return manifest

    # -------------------------------------------------------------------------
    # PRIVATE METHODS
    # -------------------------------------------------------------------------

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """Load a single YAML file."""
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}

    def _discover_table_files(self) -> List[str]:
        """Find all table YAML files (excludes _ prefixed meta-files)."""
        pattern = os.path.join(self.securables_path, "**", "*.yaml")
        all_files = glob.glob(pattern, recursive=True)
        # Exclude meta-files that start with _
        table_files = [
            f for f in all_files
            if not os.path.basename(f).startswith("_")
        ]
        return sorted(table_files)

    def _load_tables_parallel(self, table_files: List[str]) -> List[ResolvedTable]:
        """Load and resolve table configs in parallel."""
        max_workers = self._policies.get("controls", {}).get(
            "reconciliation", {}).get("max_parallel_workers", 10)

        resolved = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._resolve_table_file, f): f
                for f in table_files
            }
            for future in as_completed(futures):
                filepath = futures[future]
                try:
                    table = future.result()
                    if table:
                        resolved.append(table)
                except Exception as e:
                    logger.error(f"Error loading {filepath}: {e}")

        return sorted(resolved, key=lambda t: f"{t.catalog}.{t.schema}.{t.table_id}")

    def _resolve_table_file(self, filepath: str) -> Optional[ResolvedTable]:
        """Load a single table file and resolve its template."""
        raw = self._load_yaml(filepath)
        if not raw or "table_id" not in raw:
            logger.warning(f"Skipping invalid table file: {filepath}")
            return None

        template_name = raw.get("template")
        template = self._templates.get(template_name, {}) if template_name else {}

        # Resolve columns from template patterns
        resolved_columns = self._resolve_columns_from_template(
            template, raw.get("column_overrides", [])
        )

        # Resolve inherited policy bindings from schema/catalog
        inherited = self._get_inherited_policies(
            raw.get("catalog", ""), raw.get("schema", ""), template
        )

        # Merge grants: template defaults + table-specific
        merged_grants = self._merge_grants(template, raw.get("grants", []))

        return ResolvedTable(
            table_id=raw["table_id"],
            catalog=raw.get("catalog", ""),
            schema=raw.get("schema", ""),
            description=raw.get("description", ""),
            template=template_name,
            policy_bindings=raw.get("policy_bindings", []),
            inherited_policy_bindings=inherited,
            grants=merged_grants,
            columns=resolved_columns,
            column_overrides=raw.get("column_overrides", []),
            source_file=filepath,
        )

    def _resolve_columns_from_template(
        self, template: Dict[str, Any], overrides: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply template column_patterns to produce tag assignments.
        Column overrides take precedence over pattern matches.
        """
        # Overrides are returned as-is — actual column discovery happens
        # at execution time when we query information_schema
        return overrides

    def _get_inherited_policies(
        self, catalog: str, schema: str, template: Dict[str, Any]
    ) -> List[str]:
        """Determine which policies are inherited from catalog/schema."""
        inherited = []

        # From catalog
        if template.get("inherits_catalog_policies", True):
            for cat_def in self._defaults.get("catalogs", []):
                if cat_def.get("catalog_id") == catalog:
                    inherited.extend(cat_def.get("policy_bindings", []))

        # From schema
        if template.get("inherits_schema_policies", True):
            for sch_def in self._defaults.get("schemas", []):
                if (sch_def.get("schema_id") == schema
                        and sch_def.get("catalog") == catalog):
                    inherited.extend(sch_def.get("policy_bindings", []))

        # From template default bindings
        inherited.extend(template.get("default_policy_bindings", []))

        return list(dict.fromkeys(inherited))  # deduplicate, preserve order

    def _merge_grants(
        self, template: Dict[str, Any], table_grants: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge template default_grants with table-specific grants."""
        # Table-specific grants override template grants for same group
        table_groups = {g.get("group", g.get("role", "")) for g in table_grants}

        merged = []
        # Add template defaults that aren't overridden
        for grant in template.get("default_grants", []):
            role = grant.get("role", "")
            if role not in table_groups:
                merged.append(grant)

        # Add all table-specific grants
        merged.extend(table_grants)
        return merged


# =============================================================================
# TEMPLATE RESOLVER (for use at execution time)
# =============================================================================

class TemplateResolver:
    """
    Resolves template column_patterns against actual table columns
    discovered from information_schema at runtime.
    """

    def __init__(self, templates: Dict[str, Any]):
        self.templates = templates

    def resolve_column_tags(
        self,
        template_name: str,
        actual_columns: List[Dict[str, str]],
        overrides: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Given actual columns from information_schema, apply template patterns
        and merge with explicit overrides.

        Args:
            template_name: The template to apply
            actual_columns: [{"name": "email", "type": "STRING"}, ...]
            overrides: Explicit column_overrides from the table config

        Returns:
            List of column dicts with resolved tags
        """
        template = self.templates.get(template_name, {})
        patterns = template.get("column_patterns", [])

        # Build override lookup
        override_map = {o["name"]: o.get("tags", {}) for o in overrides}

        resolved = []
        for col in actual_columns:
            col_name = col["name"]
            col_type = col.get("type", "STRING")

            # Check if there's an explicit override
            if col_name in override_map:
                resolved.append({
                    "name": col_name,
                    "type": col_type,
                    "tags": override_map[col_name],
                    "source": "override",
                })
                continue

            # Apply template patterns
            matched_tags = {}
            for pattern in patterns:
                if re.match(pattern["match"], col_name, re.IGNORECASE):
                    matched_tags.update(pattern.get("tags", {}))

            resolved.append({
                "name": col_name,
                "type": col_type,
                "tags": matched_tags,
                "source": "template_pattern" if matched_tags else "unmatched",
            })

        return resolved


# =============================================================================
# AUTO-DISCOVERY ENGINE
# =============================================================================

class AutoDiscoveryEngine:
    """
    Discovers tables from information_schema that don't have explicit
    config files, and applies template-based config stubs.
    """

    def __init__(self, manifest: GovernanceManifest, spark):
        self.manifest = manifest
        self.spark = spark

    def discover_unmanaged_tables(self) -> List[Dict[str, Any]]:
        """
        Query information_schema and return tables that:
        - Match auto_discover rules
        - Don't already have explicit config files
        """
        existing_table_ids = {
            f"{t.catalog}.{t.schema}.{t.table_id}"
            for t in self.manifest.tables
        }

        unmanaged = []
        for rule in self.manifest.auto_discover_rules:
            catalog = rule["catalog"]
            schema = rule["schema"]
            template = rule["apply_template"]
            excludes = rule.get("exclude_tables", [])

            # Query information_schema
            df = self.spark.sql(f"""
                SELECT table_name, table_type
                FROM {catalog}.information_schema.tables
                WHERE table_schema = '{schema}'
                  AND table_type IN ('MANAGED', 'EXTERNAL')
                ORDER BY table_name
            """)

            for row in df.collect():
                table_name = row.table_name
                fqn = f"{catalog}.{schema}.{table_name}"

                # Skip if already managed
                if fqn in existing_table_ids:
                    continue

                # Skip if matches exclude pattern
                if self._matches_exclude(table_name, excludes):
                    continue

                unmanaged.append({
                    "table_id": table_name,
                    "catalog": catalog,
                    "schema": schema,
                    "template": template,
                    "fqn": fqn,
                })

        return unmanaged

    def generate_config_stubs(self, output_dir: str) -> List[str]:
        """
        Generate YAML config stubs for unmanaged tables.
        Returns list of generated file paths.
        """
        unmanaged = self.discover_unmanaged_tables()
        generated_files = []

        for table_info in unmanaged:
            schema = table_info["schema"]
            table_id = table_info["table_id"]
            template = table_info["template"]

            # Create domain directory if needed
            domain_dir = os.path.join(output_dir, schema)
            os.makedirs(domain_dir, exist_ok=True)

            filepath = os.path.join(domain_dir, f"{table_id}.yaml")
            if os.path.exists(filepath):
                continue

            stub = {
                "table_id": table_id,
                "catalog": table_info["catalog"],
                "schema": schema,
                "template": template,
                "description": f"Auto-discovered table: {table_info['fqn']}",
                "policy_bindings": [],
                "grants": [],
                "column_overrides": [],
            }

            with open(filepath, "w") as f:
                # Add header comment
                f.write(f"# Auto-generated config for {table_info['fqn']}\n")
                f.write(f"# Template: {template}\n")
                f.write(f"# Review and customize column_overrides as needed.\n\n")
                yaml.dump(stub, f, default_flow_style=False, sort_keys=False)

            generated_files.append(filepath)

        return generated_files

    def _matches_exclude(self, table_name: str, patterns: List[str]) -> bool:
        """Check if table name matches any exclude pattern."""
        for pattern in patterns:
            regex = pattern.replace("*", ".*")
            if re.match(regex, table_name, re.IGNORECASE):
                return True
        return False


# =============================================================================
# PARALLEL EXECUTOR
# =============================================================================

class ParallelGovernanceExecutor:
    """
    Executes governance operations (tag apply, policy create, grant)
    in parallel batches for scalability across 2000+ tables.
    """

    def __init__(self, spark, manifest: GovernanceManifest):
        self.spark = spark
        self.manifest = manifest
        self.controls = manifest.controls.get("reconciliation", {})
        self.max_workers = self.controls.get("max_parallel_workers", 20)
        self.batch_size = self.controls.get("batch_size", 50)
        self.max_retries = self.controls.get("max_retries", 3)

    def execute_in_batches(
        self,
        tables: List[ResolvedTable],
        operation_fn,
        operation_name: str = "operation",
    ) -> Dict[str, Any]:
        """
        Execute an operation across all tables in parallel batches.

        Args:
            tables: List of resolved tables to process
            operation_fn: Callable(spark, table) -> result dict
            operation_name: Name for logging

        Returns:
            Summary dict with success/failure counts and details
        """
        results = {
            "operation": operation_name,
            "total": len(tables),
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        # Process in batches
        for batch_idx in range(0, len(tables), self.batch_size):
            batch = tables[batch_idx:batch_idx + self.batch_size]
            batch_num = (batch_idx // self.batch_size) + 1
            total_batches = (len(tables) + self.batch_size - 1) // self.batch_size

            logger.info(f"[{operation_name}] Batch {batch_num}/{total_batches} "
                        f"({len(batch)} tables)")

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(
                        self._execute_with_retry, operation_fn, table
                    ): table
                    for table in batch
                }

                for future in as_completed(futures):
                    table = futures[future]
                    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
                    try:
                        result = future.result()
                        if result.get("status") == "success":
                            results["success"] += 1
                        elif result.get("status") == "skipped":
                            results["skipped"] += 1
                        else:
                            results["failed"] += 1
                        results["details"].append({"fqn": fqn, **result})
                    except Exception as e:
                        results["failed"] += 1
                        results["details"].append({
                            "fqn": fqn,
                            "status": "error",
                            "error": str(e),
                        })

        return results

    def _execute_with_retry(self, operation_fn, table: ResolvedTable) -> Dict:
        """Execute with retry logic."""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return operation_fn(self.spark, table)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    logger.warning(
                        f"Retry {attempt}/{self.max_retries} for "
                        f"{table.catalog}.{table.schema}.{table.table_id}: {e}"
                    )
        return {"status": "failed", "error": str(last_error)}
