"""
Policy Inheritance Engine

Implements hierarchical policy inheritance:
  Catalog → Schema → Table → Column

Key rules:
  1. Schema has policy_bindings (non-empty) → Policy applied ON SCHEMA covers all tables
  2. Schema has policy_bindings: [] → Check each table's own policy_bindings
  3. Inheritance is additive (catalog + schema + table policies all apply)
  4. More specific scopes don't override broader ones (unless explicitly stated)
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger("abac_mvp2.policy_inheritance")


def apply_inheritance_to_manifest(manifest: Any) -> Any:
    """
    Apply hierarchical policy inheritance to all tables in manifest.

    Args:
        manifest: GovernanceManifest object

    Returns:
        Updated manifest with inherited_policy_bindings populated
    """
    # Build lookup structures
    catalog_map = {c["catalog_id"]: c for c in manifest.catalogs}
    schema_map = {(s.get("catalog"), s.get("schema_id")): s for s in manifest.schemas}

    inheritance_stats = {
        "schemas_with_policies": 0,
        "schemas_delegating_to_tables": 0,
        "tables_with_inherited_policies": 0,
        "tables_with_direct_policies": 0,
    }

    for table in manifest.tables:
        # Collect inherited bindings from catalog and schema
        inherited = _collect_inherited_bindings(
            table,
            catalog_map.get(table.catalog),
            schema_map.get((table.catalog, table.schema))
        )

        # Store inherited bindings
        table.inherited_policy_bindings = inherited

        # Update stats
        if inherited:
            inheritance_stats["tables_with_inherited_policies"] += 1
        if table.policy_bindings:
            inheritance_stats["tables_with_direct_policies"] += 1

    # Count schema-level policies
    for schema in manifest.schemas:
        if schema.get("policy_bindings"):
            inheritance_stats["schemas_with_policies"] += 1
        else:
            inheritance_stats["schemas_delegating_to_tables"] += 1

    manifest.stats["inheritance"] = inheritance_stats

    logger.info(f"Applied policy inheritance:")
    logger.info(f"  Schemas with policies (ON SCHEMA): {inheritance_stats['schemas_with_policies']}")
    logger.info(f"  Schemas delegating to tables: {inheritance_stats['schemas_delegating_to_tables']}")
    logger.info(f"  Tables with inherited policies: {inheritance_stats['tables_with_inherited_policies']}")
    logger.info(f"  Tables with direct policies: {inheritance_stats['tables_with_direct_policies']}")

    return manifest


def _collect_inherited_bindings(
    table: Any,
    catalog_config: Dict[str, Any],
    schema_config: Dict[str, Any]
) -> List[str]:
    """
    Collect policy bindings inherited from catalog and schema levels.

    Args:
        table: ResolvedTable object
        catalog_config: Catalog configuration dict
        schema_config: Schema configuration dict

    Returns:
        List of inherited policy IDs
    """
    inherited = []

    # Catalog-level bindings (apply to all schemas/tables in catalog)
    if catalog_config:
        catalog_bindings = catalog_config.get("policy_bindings", [])
        if catalog_bindings:
            inherited.extend(catalog_bindings)
            logger.debug(f"Table {table.table_id} inherits {len(catalog_bindings)} policies from catalog {table.catalog}")

    # Schema-level bindings
    # - If non-empty: these policies apply ON SCHEMA (covering all tables)
    # - If empty []: schema delegates to per-table policy_bindings
    if schema_config:
        schema_bindings = schema_config.get("policy_bindings", [])
        if schema_bindings:
            inherited.extend(schema_bindings)
            logger.debug(f"Table {table.table_id} inherits {len(schema_bindings)} policies from schema {table.schema}")
        else:
            logger.debug(f"Schema {table.schema} has empty policy_bindings → table uses its own policies")

    return inherited
