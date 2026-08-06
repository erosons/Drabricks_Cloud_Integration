# Databricks notebook source
# DBTITLE 1,ABAC/GBAC Governance Reconciliation Engine
# MAGIC %md
# MAGIC # ABAC/GBAC Governance Reconciliation Engine
# MAGIC
# MAGIC This notebook reads the **separated** configuration files:
# MAGIC - `configs/policies.yaml` — Policy definitions (UDFs, ABAC rules, groups, controls)
# MAGIC - `configs/securables.yaml` — UC data targets (catalogs, schemas, tables, tags)
# MAGIC
# MAGIC It then **reconciles** the desired state against the UC platform by:
# MAGIC 1. Validating all prerequisites (tags, functions, groups)
# MAGIC 2. Creating governed tags
# MAGIC 3. Deploying UDFs to the governance schema
# MAGIC 4. Applying governed tags to securables
# MAGIC 5. Creating GBAC groups and granting base privileges
# MAGIC 6. Creating ABAC policies (row filters + column masks)
# MAGIC 7. Recording deployment status and detecting drift

# COMMAND ----------

# DBTITLE 1,Configuration: Set paths and mode
# Configuration
import os

# Paths to configuration files (relative to notebook location)
BASE_PATH = "/Workspace/Users/samson.eromonsei@databricks.com/ABAC/configs"
POLICIES_PATH = f"{BASE_PATH}/policies.yaml"
SECURABLES_PATH = f"{BASE_PATH}/securables.yaml"

# Deployment mode: 'dry_run' generates SQL only, 'apply' executes it
DEPLOYMENT_MODE = "dry_run"  # Change to "apply" to execute

# Governance UDF catalog/schema (where policy functions are deployed)
GOVERNANCE_CATALOG = "governance"
GOVERNANCE_SCHEMA = "policy_functions"

print(f"Policies config:   {POLICIES_PATH}")
print(f"Securables config: {SECURABLES_PATH}")
print(f"Deployment mode:   {DEPLOYMENT_MODE}")
print(f"UDF target:        {GOVERNANCE_CATALOG}.{GOVERNANCE_SCHEMA}")

# COMMAND ----------

# DBTITLE 1,Load and parse YAML configurations
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime

# Load both configuration files
with open(POLICIES_PATH, 'r') as f:
    policies_config = yaml.safe_load(f)

with open(SECURABLES_PATH, 'r') as f:
    securables_config = yaml.safe_load(f)

print(f"✓ Loaded policies.yaml  - kind: {policies_config['kind']}, version: {policies_config['metadata']['version']}")
print(f"✓ Loaded securables.yaml - kind: {securables_config['kind']}, version: {securables_config['metadata']['version']}")
print(f"")
print(f"Policies config contains:")
print(f"  - {len(policies_config.get('governed_tags', []))} governed tag definitions")
print(f"  - {len(policies_config.get('udf_registry', {}).get('row_filters', []))} row filter UDFs")
print(f"  - {len(policies_config.get('udf_registry', {}).get('column_masks', []))} column mask UDFs")
print(f"  - {len(policies_config.get('policies', {}).get('row_filters', []))} row filter policies")
print(f"  - {len(policies_config.get('policies', {}).get('column_masks', []))} column mask policies")
print(f"")
print(f"Securables config contains:")
print(f"  - {len(securables_config.get('catalogs', []))} catalogs")
print(f"  - {len(securables_config.get('schemas', []))} schemas")
print(f"  - {len(securables_config.get('tables', []))} tables")
print(f"  - {len(securables_config.get('denied_columns', []))} denied column rules")

# COMMAND ----------

# DBTITLE 1,Step 1: Validate prerequisites
# ============================================================================
# STEP 1: VALIDATE PREREQUISITES
# ============================================================================
# Ensures all cross-references between policies.yaml and securables.yaml are valid.

class ValidationResult:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
    
    def error(self, msg: str):
        self.errors.append(msg)
    
    def warn(self, msg: str):
        self.warnings.append(msg)
    
    def ok(self, msg: str):
        self.info.append(msg)
    
    @property
    def passed(self) -> bool:
        return len(self.errors) == 0
    
    def summary(self):
        status = "✓ PASSED" if self.passed else "✗ FAILED"
        print(f"\nValidation {status}")
        print(f"  Errors:   {len(self.errors)}")
        print(f"  Warnings: {len(self.warnings)}")
        print(f"  Info:     {len(self.info)}")
        if self.errors:
            print("\n  ERRORS:")
            for e in self.errors:
                print(f"    ✗ {e}")
        if self.warnings:
            print("\n  WARNINGS:")
            for w in self.warnings:
                print(f"    ⚠ {w}")


def validate_configs(policies: dict, securables: dict) -> ValidationResult:
    result = ValidationResult()
    
    # 1. Validate policy bindings in securables reference existing policies
    all_policy_ids = set()
    for p in policies.get('policies', {}).get('row_filters', []):
        all_policy_ids.add(p['policy_id'])
    for p in policies.get('policies', {}).get('column_masks', []):
        all_policy_ids.add(p['policy_id'])
    
    for catalog in securables.get('catalogs', []):
        for binding in catalog.get('policy_bindings', []):
            if binding not in all_policy_ids:
                result.error(f"Catalog '{catalog['catalog_id']}' references unknown policy: {binding}")
            else:
                result.ok(f"Catalog '{catalog['catalog_id']}' -> policy '{binding}' ✓")
    
    for schema in securables.get('schemas', []):
        for binding in schema.get('policy_bindings', []):
            if binding not in all_policy_ids:
                result.error(f"Schema '{schema['catalog']}.{schema['schema_id']}' references unknown policy: {binding}")
            else:
                result.ok(f"Schema '{schema['catalog']}.{schema['schema_id']}' -> policy '{binding}' ✓")
    
    # 2. Validate UDF references in policies exist in udf_registry
    all_udf_ids = set()
    for udf in policies.get('udf_registry', {}).get('row_filters', []):
        all_udf_ids.add(udf['function_id'])
    for udf in policies.get('udf_registry', {}).get('column_masks', []):
        all_udf_ids.add(udf['function_id'])
    
    for p in policies.get('policies', {}).get('row_filters', []):
        if p['udf'] not in all_udf_ids:
            result.error(f"Row filter policy '{p['policy_id']}' references unknown UDF: {p['udf']}")
    
    for p in policies.get('policies', {}).get('column_masks', []):
        if p['udf'] not in all_udf_ids:
            result.error(f"Column mask policy '{p['policy_id']}' references unknown UDF: {p['udf']}")
    
    # 3. Validate governed tag keys used in securables are defined in policies
    defined_tag_keys = {t['key'] for t in policies.get('governed_tags', [])}
    
    for table in securables.get('tables', []):
        for tag_key in table.get('tags', {}).keys():
            if tag_key not in defined_tag_keys:
                result.warn(f"Table '{table['table_id']}' uses tag '{tag_key}' not in governed_tags")
        for col in table.get('columns', []):
            for tag_key in col.get('tags', {}).keys():
                if tag_key not in defined_tag_keys:
                    result.warn(f"Column '{table['table_id']}.{col['name']}' uses tag '{tag_key}' not in governed_tags")
    
    # 4. Validate publication requirements
    pub_reqs = securables.get('publication_requirements', {})
    mandatory_tags = pub_reqs.get('mandatory_table_tags', [])
    
    for table in securables.get('tables', []):
        table_tags = set(table.get('tags', {}).keys())
        for req_tag in mandatory_tags:
            if req_tag not in table_tags:
                result.error(f"Table '{table['table_id']}' missing mandatory tag: {req_tag}")
    
    # 5. Validate denied columns reference existing tables and columns
    table_columns = {}
    for table in securables.get('tables', []):
        fqn = f"{table['catalog']}.{table['schema']}.{table['table_id']}"
        table_columns[fqn] = [c['name'] for c in table.get('columns', [])]
    
    for dc in securables.get('denied_columns', []):
        if dc['table'] not in table_columns:
            result.error(f"Denied column rule references unknown table: {dc['table']}")
        elif dc['column'] not in table_columns.get(dc['table'], []):
            result.error(f"Denied column rule references unknown column: {dc['table']}.{dc['column']}")
    
    return result


validation = validate_configs(policies_config, securables_config)
validation.summary()

# COMMAND ----------

# DBTITLE 1,Step 2: Generate governed tag SQL
# ============================================================================
# STEP 2: GENERATE GOVERNED TAG CREATION
# ============================================================================
# Governed tags cannot be created via SQL - they require the SDK.
# This step generates the SDK code and also the tag ASSIGNMENT SQL.

def generate_governed_tag_sdk_code(policies: dict) -> str:
    """Generate Python SDK code to create governed tags."""
    lines = [
        "from databricks.sdk import WorkspaceClient",
        "from databricks.sdk.service.tags import TagPolicy, Value",
        "",
        "w = WorkspaceClient()",
        "",
        "# Create governed tags (idempotent - will skip if exists)",
    ]
    
    for tag in policies.get('governed_tags', []):
        tag_key = tag['key']
        values = tag.get('allowed_values', [])
        desc = tag.get('description', '')
        
        if values:
            values_str = ", ".join([f'Value(name="{v}")' for v in values])
            lines.append(f"")
            lines.append(f"# {desc}")
            lines.append(f"try:")
            lines.append(f"    w.tag_policies.create_tag_policy(")
            lines.append(f"        tag_policy=TagPolicy(")
            lines.append(f"            tag_key='{tag_key}',")
            lines.append(f"            description='{desc}',")
            lines.append(f"            values=[{values_str}]")
            lines.append(f"        )")
            lines.append(f"    )")
            lines.append(f"    print(f'Created governed tag: {tag_key}')")
            lines.append(f"except Exception as e:")
            lines.append(f"    if 'already exists' in str(e).lower():")
            lines.append(f"        print(f'Tag already exists: {tag_key}')")
            lines.append(f"    else:")
            lines.append(f"        raise")
        else:
            lines.append(f"")
            lines.append(f"# {desc} (free-text values)")
            lines.append(f"try:")
            lines.append(f"    w.tag_policies.create_tag_policy(")
            lines.append(f"        tag_policy=TagPolicy(")
            lines.append(f"            tag_key='{tag_key}',")
            lines.append(f"            description='{desc}'")
            lines.append(f"        )")
            lines.append(f"    )")
            lines.append(f"    print(f'Created governed tag: {tag_key}')")
            lines.append(f"except Exception as e:")
            lines.append(f"    if 'already exists' in str(e).lower():")
            lines.append(f"        print(f'Tag already exists: {tag_key}')")
            lines.append(f"    else:")
            lines.append(f"        raise")
    
    return "\n".join(lines)


def generate_tag_assignment_sql(securables: dict) -> List[str]:
    """Generate SQL to apply governed tags to catalogs, schemas, tables, and columns."""
    statements = []
    
    # Catalog tags
    for catalog in securables.get('catalogs', []):
        cat_id = catalog['catalog_id']
        for tag_key, tag_value in catalog.get('tags', {}).items():
            statements.append(
                f"SET TAG ON CATALOG {cat_id} `{tag_key}` = `{tag_value}`;"
            )
    
    # Schema tags
    for schema in securables.get('schemas', []):
        fqn = f"{schema['catalog']}.{schema['schema_id']}"
        for tag_key, tag_value in schema.get('tags', {}).items():
            statements.append(
                f"SET TAG ON SCHEMA {fqn} `{tag_key}` = `{tag_value}`;"
            )
    
    # Table tags
    for table in securables.get('tables', []):
        fqn = f"{table['catalog']}.{table['schema']}.{table['table_id']}"
        for tag_key, tag_value in table.get('tags', {}).items():
            statements.append(
                f"SET TAG ON TABLE {fqn} `{tag_key}` = `{tag_value}`;"
            )
        # Column tags
        for col in table.get('columns', []):
            for tag_key, tag_value in col.get('tags', {}).items():
                statements.append(
                    f"SET TAG ON COLUMN {fqn}.{col['name']} `{tag_key}` = `{tag_value}`;"
                )
    
    return statements


# Generate outputs
governed_tag_sdk = generate_governed_tag_sdk_code(policies_config)
tag_assignment_sql = generate_tag_assignment_sql(securables_config)

print("=" * 70)
print("GOVERNED TAG SDK CODE (run separately to create tag definitions)")
print("=" * 70)
print(governed_tag_sdk)
print(f"\n{'=' * 70}")
print(f"TAG ASSIGNMENT SQL ({len(tag_assignment_sql)} statements)")
print("=" * 70)
for stmt in tag_assignment_sql[:10]:
    print(stmt)
if len(tag_assignment_sql) > 10:
    print(f"  ... and {len(tag_assignment_sql) - 10} more statements")

# COMMAND ----------

# DBTITLE 1,Step 3: Generate UDF deployment SQL
# ============================================================================
# STEP 3: GENERATE UDF DEPLOYMENT SQL
# ============================================================================
# Creates the row filter and column mask functions in the governance schema.

def generate_udf_sql(policies: dict) -> List[str]:
    """Generate CREATE FUNCTION statements for all policy UDFs."""
    statements = []
    udf_registry = policies.get('udf_registry', {})
    target_catalog = udf_registry.get('target_catalog', GOVERNANCE_CATALOG)
    target_schema = udf_registry.get('target_schema', GOVERNANCE_SCHEMA)
    fqn_prefix = f"{target_catalog}.{target_schema}"
    
    # Ensure governance catalog and schema exist
    statements.append(f"CREATE CATALOG IF NOT EXISTS {target_catalog};")
    statements.append(f"CREATE SCHEMA IF NOT EXISTS {fqn_prefix};")
    statements.append("")
    
    # Row filter UDFs
    statements.append("-- ========== ROW FILTER FUNCTIONS ==========")
    for udf in udf_registry.get('row_filters', []):
        func_name = f"{fqn_prefix}.{udf['function_id']}"
        params = ", ".join([f"{p['name']} {p['type']}" for p in udf['parameters']])
        body = udf['body'].strip()
        
        sql = f"""CREATE OR REPLACE FUNCTION {func_name}({params})
RETURNS {udf['returns']}
COMMENT '{udf['description']}'
{body}"""
        statements.append(sql)
        statements.append("")
    
    # Column mask UDFs
    statements.append("-- ========== COLUMN MASK FUNCTIONS ==========")
    for udf in udf_registry.get('column_masks', []):
        func_name = f"{fqn_prefix}.{udf['function_id']}"
        params = ", ".join([f"{p['name']} {p['type']}" for p in udf['parameters']])
        body = udf['body'].strip()
        
        sql = f"""CREATE OR REPLACE FUNCTION {func_name}({params})
RETURNS {udf['returns']}
COMMENT '{udf['description']}'
{body}"""
        statements.append(sql)
        statements.append("")
    
    return statements


udf_statements = generate_udf_sql(policies_config)

print("=" * 70)
print(f"UDF DEPLOYMENT SQL ({len([s for s in udf_statements if s.startswith('CREATE')])} functions)")
print("=" * 70)
for stmt in udf_statements:
    print(stmt)

# COMMAND ----------

# DBTITLE 1,Step 4: Generate group and privilege SQL
# ============================================================================
# STEP 4: GENERATE GROUP CREATION AND PRIVILEGE GRANTS
# ============================================================================
# Creates GBAC groups and applies base RBAC privileges.

def generate_group_and_grant_sql(securables: dict) -> tuple:
    """Generate group creation SDK code and GRANT SQL statements."""
    group_sdk_lines = [
        "from databricks.sdk import WorkspaceClient",
        "from databricks.sdk.service.iam import Group",
        "",
        "w = WorkspaceClient()",
        "",
        "# Create GBAC groups (idempotent)",
    ]
    
    grant_statements = []
    all_groups = set()
    
    for table in securables.get('tables', []):
        fqn = f"{table['catalog']}.{table['schema']}.{table['table_id']}"
        
        # Collect group names
        for role, group_name in table.get('groups', {}).items():
            all_groups.add(group_name)
        
        # Generate GRANT statements
        for grant in table.get('grants', []):
            group = grant['group']
            for priv in grant['privileges']:
                if priv == 'USE CATALOG':
                    grant_statements.append(
                        f"GRANT USE CATALOG ON CATALOG {table['catalog']} TO `{group}`;")
                elif priv == 'USE SCHEMA':
                    grant_statements.append(
                        f"GRANT USE SCHEMA ON SCHEMA {table['catalog']}.{table['schema']} TO `{group}`;")
                elif priv in ('SELECT', 'MODIFY'):
                    grant_statements.append(
                        f"GRANT {priv} ON TABLE {fqn} TO `{group}`;")
    
    # Generate SDK code for group creation
    for group_name in sorted(all_groups):
        group_sdk_lines.append(f"")
        group_sdk_lines.append(f"try:")
        group_sdk_lines.append(f"    w.groups.create(display_name='{group_name}')")
        group_sdk_lines.append(f"    print(f'Created group: {group_name}')")
        group_sdk_lines.append(f"except Exception as e:")
        group_sdk_lines.append(f"    if 'already exists' in str(e).lower():")
        group_sdk_lines.append(f"        print(f'Group exists: {group_name}')")
        group_sdk_lines.append(f"    else:")
        group_sdk_lines.append(f"        raise")
    
    # Deduplicate grants (USE CATALOG/SCHEMA may repeat)
    grant_statements = list(dict.fromkeys(grant_statements))
    
    return "\n".join(group_sdk_lines), grant_statements


group_sdk_code, grant_sql = generate_group_and_grant_sql(securables_config)

print("=" * 70)
print("GROUP CREATION SDK CODE")
print("=" * 70)
print(group_sdk_code)
print(f"\n{'=' * 70}")
print(f"PRIVILEGE GRANTS ({len(grant_sql)} statements)")
print("=" * 70)
for stmt in grant_sql[:15]:
    print(stmt)
if len(grant_sql) > 15:
    print(f"  ... and {len(grant_sql) - 15} more statements")

# COMMAND ----------

# DBTITLE 1,Step 5: Generate ABAC policy SQL
# ============================================================================
# STEP 5: GENERATE ABAC POLICY SQL
# ============================================================================
# This is the core reconciliation step. It maps policy definitions from
# policies.yaml to specific securables from securables.yaml using the
# policy_bindings references.

def resolve_policy_scope_target(policy_id: str, policies: dict, securables: dict) -> List[dict]:
    """
    Find which securables bind to a given policy_id.
    Returns a list of {scope_level, target_name} dicts.
    """
    targets = []
    
    # Check catalog bindings
    for catalog in securables.get('catalogs', []):
        if policy_id in catalog.get('policy_bindings', []):
            targets.append({
                'scope_level': 'catalog',
                'target_name': catalog['catalog_id']
            })
    
    # Check schema bindings
    for schema in securables.get('schemas', []):
        if policy_id in schema.get('policy_bindings', []):
            targets.append({
                'scope_level': 'schema',
                'target_name': f"{schema['catalog']}.{schema['schema_id']}"
            })
    
    return targets


def resolve_principal_template(principal: str, domain: str, product: str) -> str:
    """Resolve {domain} and {product} placeholders in principal names."""
    return principal.replace('{domain}', domain).replace('{product}', product)


def get_domain_product_for_target(target_name: str, securables: dict) -> tuple:
    """Get the domain and product for a given securable target."""
    # Check schemas
    for schema in securables.get('schemas', []):
        fqn = f"{schema['catalog']}.{schema['schema_id']}"
        if fqn == target_name:
            dp = schema.get('data_product', {})
            return dp.get('domain', 'unknown'), dp.get('product_id', 'unknown')
    
    # Check catalogs
    for catalog in securables.get('catalogs', []):
        if catalog['catalog_id'] == target_name:
            return 'platform', catalog['catalog_id']
    
    return 'unknown', 'unknown'


def generate_abac_policy_sql(policies: dict, securables: dict) -> List[str]:
    """Generate CREATE POLICY statements from policies.yaml mapped to securables.yaml targets."""
    statements = []
    udf_registry = policies.get('udf_registry', {})
    udf_prefix = f"{udf_registry.get('target_catalog', GOVERNANCE_CATALOG)}.{udf_registry.get('target_schema', GOVERNANCE_SCHEMA)}"
    
    # Row Filter Policies
    statements.append("-- ========== ABAC ROW FILTER POLICIES ==========")
    for policy in policies.get('policies', {}).get('row_filters', []):
        policy_id = policy['policy_id']
        targets = resolve_policy_scope_target(policy_id, policies, securables)
        
        if not targets:
            statements.append(f"-- WARNING: Policy '{policy_id}' has no securable bindings")
            continue
        
        for target in targets:
            domain, product = get_domain_product_for_target(target['target_name'], securables)
            scope_keyword = target['scope_level'].upper()
            target_name = target['target_name']
            udf_name = f"{udf_prefix}.{policy['udf']}"
            
            # Resolve principals
            to_principals = ", ".join([
                resolve_principal_template(p, domain, product) 
                for p in policy['principals']['to']
            ])
            except_principals = ", ".join([
                resolve_principal_template(p, domain, product) 
                for p in policy['principals'].get('except', [])
            ])
            
            # Build WHEN clause
            when_clause = ""
            if policy.get('when'):
                when_conditions = " AND ".join(policy['when'])
                when_clause = f"\nWHEN {when_conditions}"
            
            # Build MATCH COLUMNS clause
            match_cols = ""
            if policy.get('match_columns'):
                match_parts = [f"{mc['condition']} AS {mc['alias']}" for mc in policy['match_columns']]
                match_cols = f"\nMATCH COLUMNS {', '.join(match_parts)}"
            
            # Build USING COLUMNS clause
            using_cols = ""
            if policy.get('using_columns'):
                using_cols = f"\nUSING COLUMNS ({', '.join(policy['using_columns'])})"
            
            # Build EXCEPT clause
            except_clause = ""
            if except_principals:
                except_clause = f" EXCEPT {except_principals}"
            
            sql = f"""CREATE OR REPLACE POLICY {policy_id}
ON {scope_keyword} {target_name}
COMMENT '{policy.get('description', '')}'
ROW FILTER {udf_name}
TO {to_principals}{except_clause}
FOR TABLES{when_clause}{match_cols}{using_cols};"""
            statements.append(sql)
            statements.append("")
    
    # Column Mask Policies
    statements.append("-- ========== ABAC COLUMN MASK POLICIES ==========")
    for policy in policies.get('policies', {}).get('column_masks', []):
        policy_id = policy['policy_id']
        targets = resolve_policy_scope_target(policy_id, policies, securables)
        
        if not targets:
            statements.append(f"-- WARNING: Policy '{policy_id}' has no securable bindings")
            continue
        
        for target in targets:
            domain, product = get_domain_product_for_target(target['target_name'], securables)
            scope_keyword = target['scope_level'].upper()
            target_name = target['target_name']
            udf_name = f"{udf_prefix}.{policy['udf']}"
            
            # Resolve principals
            to_principals = ", ".join([
                resolve_principal_template(p, domain, product) 
                for p in policy['principals']['to']
            ])
            except_principals = ", ".join([
                resolve_principal_template(p, domain, product) 
                for p in policy['principals'].get('except', [])
            ])
            
            # Build WHEN clause
            when_clause = ""
            if policy.get('when'):
                when_conditions = " AND ".join(policy['when'])
                when_clause = f"\nWHEN {when_conditions}"
            
            # Build MATCH COLUMNS
            match_parts = [f"{mc['condition']} AS {mc['alias']}" for mc in policy['match_columns']]
            match_cols = f"\nMATCH COLUMNS {', '.join(match_parts)}"
            
            # Build ON COLUMN
            on_column = f"\nON COLUMN {policy['on_column']}"
            
            # Build USING COLUMNS
            using_cols = ""
            if policy.get('using_columns'):
                using_cols = f"\nUSING COLUMNS ({', '.join(policy['using_columns'])})"
            
            # Build EXCEPT clause
            except_clause = ""
            if except_principals:
                except_clause = f" EXCEPT {except_principals}"
            
            sql = f"""CREATE OR REPLACE POLICY {policy_id}
ON {scope_keyword} {target_name}
COMMENT '{policy.get('description', '')}'
COLUMN MASK {udf_name}
TO {to_principals}{except_clause}
FOR TABLES{when_clause}{match_cols}{on_column}{using_cols};"""
            statements.append(sql)
            statements.append("")
    
    return statements


abac_statements = generate_abac_policy_sql(policies_config, securables_config)

print("=" * 70)
print(f"ABAC POLICY SQL ({len([s for s in abac_statements if s.startswith('CREATE')])} policies)")
print("=" * 70)
for stmt in abac_statements:
    print(stmt)

# COMMAND ----------

# DBTITLE 1,Step 6: Generate deployment plan
# ============================================================================
# STEP 6: FULL DEPLOYMENT PLAN
# ============================================================================
# Assembles all SQL into an ordered execution plan.

def generate_deployment_plan(policies: dict, securables: dict) -> dict:
    """Generate the complete ordered deployment plan."""
    plan = {
        'timestamp': datetime.now().isoformat(),
        'mode': DEPLOYMENT_MODE,
        'policies_version': policies['metadata']['version'],
        'securables_version': securables['metadata']['version'],
        'steps': []
    }
    
    # Step 1: Governed tags (SDK)
    plan['steps'].append({
        'order': 1,
        'name': 'Create Governed Tags',
        'type': 'sdk',
        'description': 'Create governed tag definitions via Python SDK',
        'code': governed_tag_sdk,
        'statement_count': len(policies.get('governed_tags', []))
    })
    
    # Step 2: UDF deployment
    plan['steps'].append({
        'order': 2,
        'name': 'Deploy Policy UDFs',
        'type': 'sql',
        'description': 'Create row filter and column mask functions',
        'statements': udf_statements,
        'statement_count': len([s for s in udf_statements if s.startswith('CREATE')])
    })
    
    # Step 3: Tag assignments
    plan['steps'].append({
        'order': 3,
        'name': 'Apply Governed Tags',
        'type': 'sql',
        'description': 'Apply governed tags to catalogs, schemas, tables, and columns',
        'statements': tag_assignment_sql,
        'statement_count': len(tag_assignment_sql)
    })
    
    # Step 4: Groups (SDK)
    plan['steps'].append({
        'order': 4,
        'name': 'Create GBAC Groups',
        'type': 'sdk',
        'description': 'Create data product groups via Python SDK',
        'code': group_sdk_code,
        'statement_count': len(set(
            g for t in securables.get('tables', []) 
            for g in t.get('groups', {}).values()
        ))
    })
    
    # Step 5: Privilege grants
    plan['steps'].append({
        'order': 5,
        'name': 'Grant Base Privileges',
        'type': 'sql',
        'description': 'Apply RBAC privilege grants to groups',
        'statements': grant_sql,
        'statement_count': len(grant_sql)
    })
    
    # Step 6: ABAC policies
    plan['steps'].append({
        'order': 6,
        'name': 'Deploy ABAC Policies',
        'type': 'sql',
        'description': 'Create row filter and column mask ABAC policies',
        'statements': abac_statements,
        'statement_count': len([s for s in abac_statements if s.startswith('CREATE')])
    })
    
    return plan


deployment_plan = generate_deployment_plan(policies_config, securables_config)

print("=" * 70)
print("DEPLOYMENT PLAN SUMMARY")
print("=" * 70)
print(f"Timestamp:         {deployment_plan['timestamp']}")
print(f"Mode:              {deployment_plan['mode']}")
print(f"Policies version:  {deployment_plan['policies_version']}")
print(f"Securables version:{deployment_plan['securables_version']}")
print(f"")
print(f"Execution Order:")
print(f"-" * 50)
for step in deployment_plan['steps']:
    print(f"  {step['order']}. [{step['type'].upper()}] {step['name']}")
    print(f"     {step['description']}")
    print(f"     Statements: {step['statement_count']}")
    print()

# COMMAND ----------

# DBTITLE 1,Step 7: Execute deployment (controlled)
# ============================================================================
# STEP 7: EXECUTE DEPLOYMENT
# ============================================================================
# Executes the deployment plan against Unity Catalog.
# Only runs if DEPLOYMENT_MODE == 'apply'

def execute_sql_statements(statements: List[str], step_name: str) -> dict:
    """Execute a list of SQL statements and track results."""
    results = {
        'step': step_name,
        'total': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }
    
    for stmt in statements:
        # Skip comments and empty lines
        if not stmt.strip() or stmt.strip().startswith('--'):
            continue
        
        results['total'] += 1
        
        if DEPLOYMENT_MODE == 'dry_run':
            results['skipped'] += 1
            continue
        
        try:
            spark.sql(stmt.rstrip(';'))
            results['success'] += 1
        except Exception as e:
            error_msg = str(e)
            # Handle idempotent cases
            if 'already exists' in error_msg.lower():
                results['success'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({
                    'statement': stmt[:100],
                    'error': error_msg[:200]
                })
    
    return results


def run_deployment(plan: dict) -> List[dict]:
    """Execute the full deployment plan."""
    all_results = []
    
    print(f"\n{'=' * 70}")
    print(f"EXECUTING DEPLOYMENT (mode: {DEPLOYMENT_MODE})")
    print(f"{'=' * 70}\n")
    
    for step in plan['steps']:
        print(f"Step {step['order']}: {step['name']}")
        
        if step['type'] == 'sdk':
            if DEPLOYMENT_MODE == 'apply':
                print(f"  → Executing SDK code...")
                try:
                    exec(step['code'])
                    all_results.append({'step': step['name'], 'status': 'success'})
                except Exception as e:
                    all_results.append({'step': step['name'], 'status': 'failed', 'error': str(e)})
                    print(f"  ✗ Failed: {e}")
            else:
                print(f"  → [DRY RUN] Would execute SDK code ({step['statement_count']} operations)")
                all_results.append({'step': step['name'], 'status': 'dry_run'})
        
        elif step['type'] == 'sql':
            result = execute_sql_statements(step['statements'], step['name'])
            all_results.append(result)
            
            if DEPLOYMENT_MODE == 'dry_run':
                print(f"  → [DRY RUN] Would execute {result['total']} SQL statements")
            else:
                print(f"  → Executed: {result['success']} success, {result['failed']} failed")
                if result['errors']:
                    for err in result['errors'][:3]:
                        print(f"    ✗ {err['statement'][:60]}... → {err['error'][:80]}")
        
        print()
    
    return all_results


deployment_results = run_deployment(deployment_plan)

# COMMAND ----------

# DBTITLE 1,Step 8: Export full SQL script
# ============================================================================
# STEP 8: EXPORT FULL SQL SCRIPT
# ============================================================================
# Generates a single consolidated SQL script for review or manual execution.

def export_full_sql_script(plan: dict) -> str:
    """Export the complete deployment as a single SQL script."""
    lines = [
        "-- ============================================================================",
        "-- ABAC/GBAC GOVERNANCE DEPLOYMENT SCRIPT",
        f"-- Generated: {plan['timestamp']}",
        f"-- Policies version: {plan['policies_version']}",
        f"-- Securables version: {plan['securables_version']}",
        "-- ============================================================================",
        "",
    ]
    
    for step in plan['steps']:
        if step['type'] == 'sql':
            lines.append(f"-- {'=' * 68}")
            lines.append(f"-- STEP {step['order']}: {step['name'].upper()}")
            lines.append(f"-- {step['description']}")
            lines.append(f"-- {'=' * 68}")
            lines.append("")
            for stmt in step['statements']:
                lines.append(stmt)
            lines.append("")
        elif step['type'] == 'sdk':
            lines.append(f"-- {'=' * 68}")
            lines.append(f"-- STEP {step['order']}: {step['name'].upper()} (requires Python SDK)")
            lines.append(f"-- {step['description']}")
            lines.append(f"-- Run the following in a Python notebook or script:")
            lines.append(f"-- {'=' * 68}")
            for code_line in step['code'].split('\n'):
                lines.append(f"-- {code_line}")
            lines.append("")
    
    return "\n".join(lines)


full_script = export_full_sql_script(deployment_plan)

# Save to file
script_path = f"{BASE_PATH}/../generated/deployment_script.sql"
import os
os.makedirs(os.path.dirname(script_path), exist_ok=True)
with open(script_path, 'w') as f:
    f.write(full_script)

print(f"✓ Full deployment script exported to: {script_path}")
print(f"  Total lines: {len(full_script.splitlines())}")
print(f"\nFirst 50 lines:")
print("\n".join(full_script.splitlines()[:50]))

# COMMAND ----------

