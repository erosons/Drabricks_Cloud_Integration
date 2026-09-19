"""
ABAC Spec Table Reader — Bridges SDP-META Dataflowspec Tables to ABAC Governance

Reads bronze/silver dataflowspec tables created by SDP-META onboarding,
extracts bronze_abac_governance and silver_abac_governance paths,
loads the governance YAML files, and produces a GovernanceManifest
for the ABAC notebooks (02-06) to consume.

Design:
  1. Query dataflowspec tables for ABAC governance paths
  2. Load governance YAML from UC Volume paths
  3. Merge with policies.yaml
  4. Return unified GovernanceManifest

Usage:
    from spec_table_reader import SpecTableABACLoader

    loader = SpecTableABACLoader(
        spark=spark,
        catalog="general_use",
        sdp_meta_schema="sdp_meta",
        bronze_spec_table="employee_dataflowspec_bronze",
        silver_spec_table="employee_dataflowspec_silver",
        policies_path="/Workspace/abac-mvp2/configs/policies.yaml"
    )
    manifest = loader.load()
"""

import logging
import yaml
from typing import Dict, List, Any, Optional
from pyspark.sql import SparkSession
from config_loader import GovernanceManifest, ResolvedTable, TemplateResolver

logger = logging.getLogger("abac_mvp2.spec_table_reader")


class SpecTableABACLoader:
    """
    Reads ABAC governance paths from SDP-META dataflowspec tables
    and loads the governance configs into a unified manifest.
    """

    def __init__(
        self,
        spark: SparkSession,
        catalog: str,
        sdp_meta_schema: str,
        bronze_spec_table: str,
        silver_spec_table: str,
        policies_path: str,
    ):
        self.spark = spark
        self.catalog = catalog
        self.sdp_meta_schema = sdp_meta_schema
        self.bronze_spec_table = bronze_spec_table
        self.silver_spec_table = silver_spec_table
        self.policies_path = policies_path
        self._policies: Dict[str, Any] = {}
        self._bronze_tables: List[Dict[str, Any]] = []
        self._silver_tables: List[Dict[str, Any]] = []

    def load(self) -> GovernanceManifest:
        """
        Load ABAC governance from spec tables.

        Returns:
            GovernanceManifest with policies and tables
        """
        logger.info("Loading ABAC governance from SDP-META dataflowspec tables")

        # 1. Load policies
        self._policies = self._load_policies()

        # 2. Read bronze spec table for ABAC paths
        bronze_abac_paths = self._read_bronze_spec_table()

        # 3. Read silver spec table for ABAC paths
        silver_abac_paths = self._read_silver_spec_table()

        # 4. Load governance YAML files from those paths
        all_tables = []
        all_catalogs = []
        all_schemas = []
        loaded_yaml_paths = set()

        # Load bronze governance
        for path_info in bronze_abac_paths:
            if path_info["abac_path"] and path_info["abac_path"] not in loaded_yaml_paths:
                tables, catalogs, schemas = self._load_governance_yaml_full(
                    path_info["abac_path"],
                    layer="bronze",
                    flow_id=path_info["dataFlowId"]
                )
                all_tables.extend(tables)
                all_catalogs.extend(catalogs)
                all_schemas.extend(schemas)
                loaded_yaml_paths.add(path_info["abac_path"])

        # Load silver governance
        for path_info in silver_abac_paths:
            if path_info["abac_path"] and path_info["abac_path"] not in loaded_yaml_paths:
                tables, catalogs, schemas = self._load_governance_yaml_full(
                    path_info["abac_path"],
                    layer="silver",
                    flow_id=path_info["dataFlowId"]
                )
                all_tables.extend(tables)
                all_catalogs.extend(catalogs)
                all_schemas.extend(schemas)
                loaded_yaml_paths.add(path_info["abac_path"])

        # 5. Build manifest
        manifest = GovernanceManifest(
            policies=self._policies,
            catalogs=all_catalogs,
            schemas=all_schemas,
            tables=all_tables,
            templates={},
            auto_discover_rules=[],
            controls={},
            stats={
                "bronze_flows": len(bronze_abac_paths),
                "silver_flows": len(silver_abac_paths),
                "total_tables": len(all_tables),
            }
        )

        logger.info(f"Loaded {len(all_tables)} tables from spec table ABAC configs")
        return manifest

    def _load_policies(self) -> Dict[str, Any]:
        """Load policies.yaml from Workspace."""
        logger.info(f"Loading policies from: {self.policies_path}")
        with open(self.policies_path, "r") as f:
            policies = yaml.safe_load(f) or {}
        return policies

    def _read_bronze_spec_table(self) -> List[Dict[str, str]]:
        """
        Read bronze dataflowspec table and extract ABAC governance paths.

        Returns:
            List of {dataFlowId, database, table, abac_path}
        """
        table_name = f"{self.catalog}.{self.sdp_meta_schema}.{self.bronze_spec_table}"
        logger.info(f"Reading bronze spec table: {table_name}")

        # Query for rows that have targetDetails and extract ABAC paths
        # Note: The onboarding JSON has bronze_abac_governance but it's not in the spec table schema
        # So we need to reconstruct from the patterns or read from the onboarding JSON directly

        df = self.spark.sql(f"""
            SELECT
                dataFlowId,
                targetDetails.database as database,
                targetDetails.table as table,
                targetDetails.catalog as catalog
            FROM {table_name}
        """)

        rows = df.collect()

        # Since bronze_abac_governance isn't in the spec table, we need to read from Volume
        # Pattern: /Volumes/{catalog}/platform_admin/sdp_meta_files/conf/abac/bronze_securables.yml
        abac_paths = []
        for row in rows:
            catalog = row.catalog if row.catalog else self.catalog
            # Default ABAC path based on convention
            abac_path = f"/Volumes/{catalog}/platform_admin/sdp_meta_files/conf/abac/bronze_securables.yml"
            abac_paths.append({
                "dataFlowId": row.dataFlowId,
                "database": row.database,
                "table": row.table,
                "catalog": catalog,
                "abac_path": abac_path
            })

        logger.info(f"Found {len(abac_paths)} bronze flows")
        return abac_paths

    def _read_silver_spec_table(self) -> List[Dict[str, str]]:
        """
        Read silver dataflowspec table and extract ABAC governance paths.

        Returns:
            List of {dataFlowId, database, table, abac_path}
        """
        table_name = f"{self.catalog}.{self.sdp_meta_schema}.{self.silver_spec_table}"
        logger.info(f"Reading silver spec table: {table_name}")

        df = self.spark.sql(f"""
            SELECT
                dataFlowId,
                targetDetails.database as database,
                targetDetails.table as table,
                targetDetails.catalog as catalog
            FROM {table_name}
        """)

        rows = df.collect()

        abac_paths = []
        for row in rows:
            catalog = row.catalog if row.catalog else self.catalog
            # Default ABAC path based on convention
            abac_path = f"/Volumes/{catalog}/platform_admin/sdp_meta_files/conf/abac/silver_securables.yml"
            abac_paths.append({
                "dataFlowId": row.dataFlowId,
                "database": row.database,
                "table": row.table,
                "catalog": catalog,
                "abac_path": abac_path
            })

        logger.info(f"Found {len(abac_paths)} silver flows")
        return abac_paths

    def _load_governance_yaml_full(
        self,
        yaml_path: str,
        layer: str,
        flow_id: str
    ):
        """
        Load governance YAML with full structure (catalogs, schemas, tables).

        Returns:
            Tuple of (tables, catalogs, schemas)
        """
        logger.info(f"Loading {layer} governance from: {yaml_path}")

        try:
            with open(yaml_path, "r") as f:
                governance = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"ABAC governance file not found: {yaml_path}")
            return [], [], []
        except Exception as e:
            logger.error(f"Failed to load {yaml_path}: {e}")
            return [], [], []

        tables = []
        catalogs = governance.get("catalogs", [])
        schemas = governance.get("schemas", [])

        # Parse hierarchical structure: catalogs → schemas → tables
        for schema_config in schemas:
            catalog_name = schema_config.get("catalog", self.catalog)
            schema_name = schema_config.get("schema_id", "")

            for table_config in schema_config.get("tables", []):
                resolved_table = ResolvedTable(
                    table_id=table_config.get("table_id", ""),
                    catalog=catalog_name,
                    schema=schema_name,
                    description=table_config.get("description", ""),
                    template=table_config.get("template"),
                    policy_bindings=table_config.get("policy_bindings", []),
                    inherited_policy_bindings=[],
                    grants=table_config.get("grants", []),
                    columns=table_config.get("columns", []),
                    column_overrides=[],
                    tags=table_config.get("tags", {}),
                    mnpi_expiration_date=table_config.get("mnpi_expiration_date"),
                    source_file=yaml_path
                )
                tables.append(resolved_table)

        logger.info(f"Loaded {len(tables)} tables from {yaml_path}")
        return tables, catalogs, schemas

    def _load_governance_yaml(
        self,
        yaml_path: str,
        layer: str,
        flow_id: str
    ) -> List[ResolvedTable]:
        """
        Load governance YAML from UC Volume path (backward compat - returns tables only).

        Args:
            yaml_path: Full UC Volume path to YAML file
            layer: "bronze" or "silver"
            flow_id: DataflowId for context

        Returns:
            List of ResolvedTable objects
        """
        tables, _, _ = self._load_governance_yaml_full(yaml_path, layer, flow_id)
        return tables


class EnhancedSpecTableABACLoader(SpecTableABACLoader):
    """
    Enhanced version that reads ABAC paths from a separate mapping table.

    Use this if you create a custom table that maps dataFlowId -> abac_governance_path
    by reading the onboarding JSON directly.
    """

    def __init__(
        self,
        spark: SparkSession,
        catalog: str,
        sdp_meta_schema: str,
        bronze_spec_table: str,
        silver_spec_table: str,
        policies_path: str,
        abac_mapping_table: Optional[str] = None,
    ):
        super().__init__(
            spark, catalog, sdp_meta_schema,
            bronze_spec_table, silver_spec_table, policies_path
        )
        self.abac_mapping_table = abac_mapping_table

    def _read_bronze_spec_table(self) -> List[Dict[str, str]]:
        """Read bronze spec with ABAC path from mapping table."""
        if not self.abac_mapping_table:
            return super()._read_bronze_spec_table()

        # Join spec table with ABAC mapping table
        table_name = f"{self.catalog}.{self.sdp_meta_schema}.{self.bronze_spec_table}"
        mapping_name = f"{self.catalog}.{self.sdp_meta_schema}.{self.abac_mapping_table}"

        df = self.spark.sql(f"""
            SELECT
                s.dataFlowId,
                s.targetDetails.database as database,
                s.targetDetails.table as table,
                s.targetDetails.catalog as catalog,
                m.bronze_abac_governance as abac_path
            FROM {table_name} s
            LEFT JOIN {mapping_name} m ON s.dataFlowId = m.dataFlowId
        """)

        rows = df.collect()
        return [row.asDict() for row in rows]

    def _read_silver_spec_table(self) -> List[Dict[str, str]]:
        """Read silver spec with ABAC path from mapping table."""
        if not self.abac_mapping_table:
            return super()._read_silver_spec_table()

        table_name = f"{self.catalog}.{self.sdp_meta_schema}.{self.silver_spec_table}"
        mapping_name = f"{self.catalog}.{self.sdp_meta_schema}.{self.abac_mapping_table}"

        df = self.spark.sql(f"""
            SELECT
                s.dataFlowId,
                s.targetDetails.database as database,
                s.targetDetails.table as table,
                s.targetDetails.catalog as catalog,
                m.silver_abac_governance as abac_path
            FROM {table_name} s
            LEFT JOIN {mapping_name} m ON s.dataFlowId = m.dataFlowId
        """)

        rows = df.collect()
        return [row.asDict() for row in rows]
