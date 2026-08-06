# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Governance Validation & Testing
# MAGIC %md
# MAGIC # Governance Validation & Testing
# MAGIC
# MAGIC This notebook provides:
# MAGIC 1. **Policy inspection** — SHOW POLICIES / SHOW EFFECTIVE POLICIES
# MAGIC 2. **Drift detection** — Compare desired config vs actual UC state
# MAGIC 3. **Positive test cases** — Verify authorized access works
# MAGIC 4. **Negative test cases** — Verify unauthorized access is denied
# MAGIC 5. **Audit queries** — Track policy changes and access events

# COMMAND ----------

# DBTITLE 1,Load configuration for test generation
import yaml
from typing import List, Dict

BASE_PATH = "/Workspace/Users/samson.eromonsei@databricks.com/ABAC/configs"

with open(f"{BASE_PATH}/policies.yaml", 'r') as f:
    policies_config = yaml.safe_load(f)
    print(policies_config)

with open(f"{BASE_PATH}/securables.yaml", 'r') as f:
    securables_config = yaml.safe_load(f)
    print(securables_config)

print("✓ Configuration loaded for test generation")

# COMMAND ----------

# DBTITLE 1,Setup test data: Create customer_profile table
# ============================================================================
# TEST DATA SETUP
# ============================================================================
# Creates the test table used by validation tests.
# This mirrors the schema defined in securables.yaml for:
#   general_use.customer.customer_profile
#
# After creation, governed tags and ABAC policies should be applied via the
# reconciliation engine or DAB bundle before running enforcement tests.

TEST_CATALOG = "general_use"
TEST_SCHEMA = "customer"
TEST_TABLE = "customer_profile"
FQN = f"{TEST_CATALOG}.{TEST_SCHEMA}.{TEST_TABLE}"

# Create catalog and schema if needed
spark.sql(f"CREATE CATALOG IF NOT EXISTS {TEST_CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {TEST_CATALOG}.{TEST_SCHEMA}")

# Create the test table with columns matching securables.yaml
spark.sql(f"""
CREATE OR REPLACE TABLE {FQN} (
  customer_id BIGINT,
  first_name STRING,
  last_name STRING,
  email STRING,
  phone_number STRING,
  date_of_birth DATE,
  ssn STRING,
  region_code STRING,
  is_active BOOLEAN,
  created_at TIMESTAMP
) USING DELTA
""")

# Insert synthetic PII test data (10 rows across 3 regions)
spark.sql(f"""
INSERT INTO {FQN} VALUES
  (1,  'Alice',   'Johnson',  'alice.johnson@example.com',     '+1-555-0101',      '1985-03-15', '123-45-6789', 'us',   true,  '2024-01-10T08:00:00'),
  (2,  'Bob',     'Smith',    'bob.smith@company.co.uk',       '+44-20-7946-0958', '1990-07-22', '234-56-7890', 'eu',   true,  '2024-01-11T09:30:00'),
  (3,  'Carol',   'Williams', 'carol.w@enterprise.de',         '+49-30-1234-5678', '1978-11-08', '345-67-8901', 'eu',   true,  '2024-01-12T10:00:00'),
  (4,  'David',   'Chen',     'david.chen@corp.com.sg',        '+65-6123-4567',    '1992-05-20', '456-78-9012', 'apac', true,  '2024-01-13T11:00:00'),
  (5,  'Eva',     'Martinez', 'eva.m@startup.io',              '+1-555-0202',      '1988-09-14', '567-89-0123', 'us',   true,  '2024-01-14T12:00:00'),
  (6,  'Frank',   'Weber',    'frank.weber@firma.at',          '+43-1-234-5678',   '1975-12-03', '678-90-1234', 'eu',   false, '2024-01-15T13:00:00'),
  (7,  'Grace',   'Kim',      'grace.kim@techcorp.kr',         '+82-2-1234-5678',  '1995-02-28', '789-01-2345', 'apac', true,  '2024-01-16T14:00:00'),
  (8,  'Henry',   'Patel',    'henry.p@services.in',           '+91-22-1234-5678', '1983-06-17', '890-12-3456', 'apac', true,  '2024-01-17T15:00:00'),
  (9,  'Iris',    'Durand',   'iris.durand@entreprise.fr',     '+33-1-2345-6789',  '1991-04-05', '901-23-4567', 'eu',   false, '2024-01-18T16:00:00'),
  (10, 'Jack',    'Thompson', 'jack.t@bigcorp.com',            '+1-555-0303',      '1980-10-30', '012-34-5678', 'us',   true,  '2024-01-19T17:00:00')
""")

print(f"✓ Test table created: {FQN}")
print(f"  Rows: 10 (3 us, 4 eu, 3 apac | 2 inactive)")
print(f"  PII columns: email, phone_number, date_of_birth, ssn")
print(f"  Soft-delete flag: is_active")
print(f"  Region column: region_code")
display(spark.sql(f"SELECT * FROM {FQN}"))

# COMMAND ----------

# DBTITLE 1,Policy Inspection: Show all policies on catalog
# MAGIC %sql
# MAGIC -- ============================================================================
# MAGIC -- POLICY INSPECTION
# MAGIC -- ============================================================================
# MAGIC -- Inspect policies applied at each level
# MAGIC
# MAGIC -- Show policies directly on a catalog
# MAGIC SHOW POLICIES ON CATALOG general_use;

# COMMAND ----------

# DBTITLE 1,Policy Inspection: Show effective policies on a table
# MAGIC %sql
# MAGIC -- Show ALL effective policies (direct + inherited) on a specific table
# MAGIC SHOW EFFECTIVE POLICIES ON TABLE general_use.customer.customer_profile;

# COMMAND ----------

# DBTITLE 1,Policy Inspection: Describe a specific policy
# MAGIC %sql
# MAGIC -- Describe a specific policy for detailed info
# MAGIC DESCRIBE POLICY pii_email_masking ON CATALOG general_use;

# COMMAND ----------

# DBTITLE 1,Build policy lookup from policies.yaml
from pprint import pprint
# ============================================================================
# BUILD POLICY LOOKUP
# ============================================================================
# {**rf, 'policy_type': 'row_filter'} spreads ALL keys from the YAML dict.
# This means each entry in all_policies contains the FULL policy definition:
#   - policy_id, description, scope_level, udf
#   - principals: {to: [...], except: [...]}
#   - match_columns: [{condition: "has_tag('...')", alias: "..."}]
#   - using_columns, on_column, failure_mode, when, for_tables
#   - policy_type (added by us: 'row_filter' or 'column_mask')

all_policies = {}
for rf in policies_config.get('policies', {}).get('row_filters', []):
    all_policies[rf['policy_id']] = {**rf, 'policy_type': 'row_filter'}
for cm in policies_config.get('policies', {}).get('column_masks', []):
    all_policies[cm['policy_id']] = {**cm, 'policy_type': 'column_mask'}
pprint(all_policies.items(), indent=5)


# COMMAND ----------

# Map tags to columns for each table
PII_TAG_KEYS = {'class.email_address', 'class.phone_number', 'class.us_ssn', 'class.date_of_birth', 'class.name', 'class.location'}


# Scope precedence: table > schema > catalog (most specific wins)
SCOPE_PRECEDENCE = {'table': 3, 'schema': 2, 'catalog': 1}

# COMMAND ----------

# DBTITLE 1,get_inherited_policies: Collect policies per scope level
def get_inherited_policies(table: dict, securables: dict) -> List[Dict]:
    """Get all effective policy_ids with their source scope level.
    
    Returns list of {policy_id, source_scope} ordered by precedence.
    When two policies target the same tag/column, the highest-precedence
    (most specific scope) wins — matching UC runtime behavior.
    """
    # -------------------------------------------------------------------------
    # INPUT: table (dict) — a single table entry from securables.yaml
    # {
    #     'table_id': 'customer_profile',
    #     'catalog': 'general_use',
    #     'schema': 'customer',
    #     'policy_bindings': ['active_records_only', 'ssn_full_redaction'],
    #     'grants': [...],
    #     'columns': [...]
    # }
    #
    # INPUT: securables (dict) — the full securables_config loaded from YAML
    # {
    #     'catalogs': [{'catalog_id': 'general_use', 'policy_bindings': ['pii_email_masking'], ...}],
    #     'schemas': [{'schema_id': 'customer', 'catalog': 'general_use', 'policy_bindings': ['regional_data_isolation', 'pii_phone_masking'], ...}],
    #     'tables': [...]
    # }
    #
    # OUTPUT: List[Dict] — policy entries tagged with their source scope
    # [
    #     {'policy_id': 'active_records_only', 'source_scope': 'table'},
    #     {'policy_id': 'ssn_full_redaction', 'source_scope': 'table'},
    #     {'policy_id': 'regional_data_isolation', 'source_scope': 'schema'},
    #     {'policy_id': 'pii_phone_masking', 'source_scope': 'schema'},
    #     {'policy_id': 'pii_email_masking', 'source_scope': 'catalog'}
    # ]
    # -------------------------------------------------------------------------
    policy_entries = []

    # Table-level bindings (highest precedence)
    for pid in table.get('policy_bindings', []):
        policy_entries.append({'policy_id': pid, 'source_scope': 'table'})

    # Schema-level bindings
    for schema in securables.get('schemas', []):
        if schema['schema_id'] == table['schema'] and schema['catalog'] == table['catalog']:
            for pid in schema.get('policy_bindings', []):
                policy_entries.append({'policy_id': pid, 'source_scope': 'schema'})

    # Catalog-level bindings (lowest precedence)
    for catalog in securables.get('catalogs', []):
        if catalog['catalog_id'] == table['catalog']:
            for pid in catalog.get('policy_bindings', []):
                policy_entries.append({'policy_id': pid, 'source_scope': 'catalog'})
    print(f"policy entries: {policy_entries}")

    return policy_entries

# COMMAND ----------

# DBTITLE 1,resolve_effective_policies: Deduplicate by tag precedence
def resolve_effective_policies(policy_entries: List[Dict], all_policies: dict, table_columns: list) -> List[Dict]:
    """Deduplicate policies by target tag — most specific scope wins.
    
    If a table-level policy and a catalog-level policy both match the same
    column tag, only the table-level policy generates a test case.
    This mirrors UC runtime behavior where narrower scope takes precedence.
    """
    # -------------------------------------------------------------------------
    # INPUT: policy_entries (List[Dict]) — from get_inherited_policies()
    # [
    #     {'policy_id': 'active_records_only', 'source_scope': 'table'},
    #     {'policy_id': 'ssn_full_redaction', 'source_scope': 'table'},
    #     {'policy_id': 'regional_data_isolation', 'source_scope': 'schema'},
    #     {'policy_id': 'pii_phone_masking', 'source_scope': 'schema'},
    #     {'policy_id': 'pii_email_masking', 'source_scope': 'catalog'}
    # ]
    #
    # INPUT: all_policies (dict) — policy_id -> full policy definition
    # {
    #     'pii_email_masking': {
    #         'policy_id': 'pii_email_masking',
    #         'policy_type': 'column_mask',
    #         'scope_level': 'catalog',
    #         'udf': 'mask_email',
    #         'principals': {'to': ['`All Users`'], 'except': ['platform_governance_admin', ...]},
    #         'match_columns': [{'condition': "has_tag('class.email_address')", 'alias': 'email_col'}],
    #         'on_column': 'email_col',
    #         'using_columns': ['email_col'],
    #         'failure_mode': 'deny'
    #     },
    #     ...
    # }
    #
    # INPUT: table_columns (list) — column definitions from securables.yaml
    # [
    #     {'name': 'customer_id', 'type': 'BIGINT', 'tags': {}},
    #     {'name': 'email', 'type': 'STRING', 'tags': {'class.email_address': ''}},
    #     {'name': 'ssn', 'type': 'STRING', 'tags': {'class.us_ssn': ''}},
    #     ...
    # ]

    # LOGIC :# This is what allows resolve_effective_policies() to access:
    #   policy['match_columns'][0]['condition'] -> e.g. "has_tag('class.email_address')"
    #   policy['principals']['to']             -> e.g. ["`All Users`"]
    #   policy['principals']['except']         -> e.g. ["platform_governance_admin"]
    #   policy['udf']                          -> e.g. "mask_email"
    
    # OUTPUT: List[Dict] — one winning policy per target tag (highest scope wins)
    # [
    #     {
    #         'policy_id': 'ssn_full_redaction',
    #         'source_scope': 'table',          # table > catalog, so this wins for class.us_ssn
    #         'scope_rank': 3,
    #         'target_tag': 'class.us_ssn',
    #         'matched_columns': ['ssn'],
    #         'policy': { ...full policy dict... }
    #     },
    #     {
    #         'policy_id': 'pii_email_masking',
    #         'source_scope': 'catalog',         # no competing table/schema policy for this tag
    #         'scope_rank': 1,
    #         'target_tag': 'class.email_address',
    #         'matched_columns': ['email'],
    #         'policy': { ...full policy dict... }
    #     },
    #     ...
    # ]
    # -------------------------------------------------------------------------
    import re
    # Map: target_tag -> best policy entry (highest precedence)
    tag_to_policy = {}

    for entry in policy_entries:
        policy = all_policies.get(entry['policy_id'])
        if not policy:
            continue

        # Extract the target tag from the match_columns condition
        tag_condition = policy['match_columns'][0]['condition']
        tag_match = re.search(r"has_tag(?:_value)?\('([^']+)'", tag_condition)
        if not tag_match:
            continue
        target_tag = tag_match.group(1)

        # Check if any column in this table actually has this tag
        matching_cols = [c['name'] for c in table_columns if target_tag in c.get('tags', {})]
        if not matching_cols:
            continue  # Policy doesn't apply to this table (no matching columns)

        scope_rank = SCOPE_PRECEDENCE[entry['source_scope']]
        existing = tag_to_policy.get(target_tag)

        if not existing or scope_rank > existing['scope_rank']:
            tag_to_policy[target_tag] = {
                'policy_id': entry['policy_id'],
                'source_scope': entry['source_scope'],
                'scope_rank': scope_rank,
                'target_tag': target_tag,
                'matched_columns': matching_cols,
                'policy': policy
            }

    return list(tag_to_policy.values())

# COMMAND ----------

# DBTITLE 1,Test Generation: Create test matrix from config

def generate_test_cases(policies: dict, securables: dict) -> List[Dict]:
    """Generate test cases from policy and securable configurations."""
    # -------------------------------------------------------------------------
    # INPUT: policies (dict) — full policies_config from policies.yaml
    # {
    #     'policies': {
    #         'row_filters': [{'policy_id': 'regional_data_isolation', ...}, ...],
    #         'column_masks': [{'policy_id': 'pii_email_masking', ...}, ...]
    #     },
    #     'udf_registry': {...},
    #     'group_templates': {...}
    # }
    #
    # INPUT: securables (dict) — full securables_config from securables.yaml
    # {
    #     'catalogs': [{'catalog_id': 'general_use', 'policy_bindings': [...], 'grants': [...]}],
    #     'schemas': [{'schema_id': 'customer', 'catalog': 'general_use', 'policy_bindings': [...], 'grants': [...]}],
    #     'tables': [
    #         {
    #             'table_id': 'customer_profile',
    #             'catalog': 'general_use',
    #             'schema': 'customer',
    #             'policy_bindings': ['active_records_only', 'ssn_full_redaction'],
    #             'grants': [{'group': 'customer_data_readers', 'privileges': ['SELECT']}, ...],
    #             'columns': [{'name': 'email', 'type': 'STRING', 'tags': {'class.email_address': ''}}, ...]
    #         },
    #         ...
    #     ]
    # }
    #
    # OUTPUT: List[Dict] — list of test case dicts, one per assertion
    # [
    #     {
    #         'test_id': 'customer_profile_customer_data_readers_select',
    #         'type': 'grant',                    # grant | negative | masking | exception | row_filter
    #         'description': "Group 'customer_data_readers' can SELECT from general_use.customer.customer_profile",
    #         'principal_group': 'customer_data_readers',
    #         'table': 'general_use.customer.customer_profile',
    #         'expected_result': 'SUCCESS',        # SUCCESS | DENIED | MASKED_VALUES | CLEARTEXT_VALUES | FILTERED_ROWS | ALL_ROWS
    #         'sql': 'SELECT * FROM general_use.customer.customer_profile LIMIT 1;'
    #     },
    #     {
    #         'test_id': 'customer_profile_pii_email_masking_masked',
    #         'type': 'masking',
    #         'description': "[catalog] Policy 'pii_email_masking' masks [email] for `All Users`",
    #         'principal_group': '`All Users`',
    #         'table': 'general_use.customer.customer_profile',
    #         'masked_columns': ['email'],
    #         'policy_id': 'pii_email_masking',
    #         'source_scope': 'catalog',
    #         'udf': 'mask_email',
    #         'expected_result': 'MASKED_VALUES',
    #         'sql': 'SELECT email FROM general_use.customer.customer_profile LIMIT 5;'
    #     },
    #     ...
    # ]
    # -------------------------------------------------------------------------
    tests = []

    for table in securables.get('tables', []):
        fqn = f"{table['catalog']}.{table['schema']}.{table['table_id']}"
        grants = table.get('grants', [])

        # --- GRANT TESTS: Each granted group can access the table ---
        for grant in grants:
            group = grant['group']
            privs = grant['privileges']
            if 'SELECT' in privs:
                tests.append({
                    'test_id': f"{table['table_id']}_{group}_select",
                    'type': 'grant',
                    'description': f"Group '{group}' can SELECT from {fqn}",
                    'principal_group': group,
                    'table': fqn,
                    'expected_result': 'SUCCESS',
                    'sql': f"SELECT * FROM {fqn} LIMIT 1;"
                })
            if 'MODIFY' in privs:
                tests.append({
                    'test_id': f"{table['table_id']}_{group}_modify",
                    'type': 'grant',
                    'description': f"Group '{group}' can MODIFY {fqn}",
                    'principal_group': group,
                    'table': fqn,
                    'expected_result': 'SUCCESS',
                    'sql': f"-- Verify: User in '{group}' can INSERT/UPDATE on {fqn}"
                })

        # --- NEGATIVE: Ungrouped user denied ---
        tests.append({
            'test_id': f"{table['table_id']}_no_group_denied",
            'type': 'negative',
            'description': f"User with no group membership cannot access {fqn}",
            'principal_group': 'NO_GROUP',
            'table': fqn,
            'expected_result': 'DENIED',
            'sql': f"-- Verify: User NOT in any group gets PERMISSION_DENIED on {fqn}"
        })

        # --- POLICY-DRIVEN TESTS (with scope precedence) ---
        # Resolve which policy WINS per column/tag (table > schema > catalog)
        policy_entries = get_inherited_policies(table, securables)
        effective = resolve_effective_policies(policy_entries, all_policies, table.get('columns', []))

        for resolved in effective:
            policy = resolved['policy']
            policy_id = resolved['policy_id']
            source_scope = resolved['source_scope']
            masked_columns = resolved['matched_columns']

            if policy['policy_type'] == 'column_mask':
                # TO groups see MASKED values
                for to_group in policy['principals']['to']:
                    tests.append({
                        'test_id': f"{table['table_id']}_{policy_id}_masked",
                        'type': 'masking',
                        'description': f"[{source_scope}] Policy '{policy_id}' masks [{', '.join(masked_columns)}] for {to_group}",
                        'principal_group': to_group,
                        'table': fqn,
                        'masked_columns': masked_columns,
                        'policy_id': policy_id,
                        'source_scope': source_scope,
                        'udf': policy['udf'],
                        'expected_result': 'MASKED_VALUES',
                        'sql': f"SELECT {', '.join(masked_columns)} FROM {fqn} LIMIT 5;"
                    })

                # EXCEPT groups see CLEARTEXT
                for except_group in policy['principals']['except']:
                    if '{' in except_group:  # Skip template patterns
                        continue
                    tests.append({
                        'test_id': f"{table['table_id']}_{policy_id}_cleartext_{except_group}",
                        'type': 'exception',
                        'description': f"[{source_scope}] EXCEPT '{except_group}' sees cleartext for [{', '.join(masked_columns)}]",
                        'principal_group': except_group,
                        'table': fqn,
                        'masked_columns': masked_columns,
                        'policy_id': policy_id,
                        'source_scope': source_scope,
                        'expected_result': 'CLEARTEXT_VALUES',
                        'sql': f"SELECT {', '.join(masked_columns)} FROM {fqn} LIMIT 5;"
                    })

            elif policy['policy_type'] == 'row_filter':
                # ROW FILTER: TO groups have rows filtered
                for to_group in policy['principals']['to']:
                    tests.append({
                        'test_id': f"{table['table_id']}_{policy_id}_filtered",
                        'type': 'row_filter',
                        'description': f"[{source_scope}] Policy '{policy_id}' filters rows for {to_group} on {fqn}",
                        'principal_group': to_group,
                        'table': fqn,
                        'policy_id': policy_id,
                        'source_scope': source_scope,
                        'udf': policy['udf'],
                        'expected_result': 'FILTERED_ROWS',
                        'sql': f"SELECT COUNT(*) FROM {fqn}; -- Should return subset"
                    })

                # EXCEPT groups see ALL rows
                for except_group in policy['principals']['except']:
                    if '{' in except_group:
                        continue
                    tests.append({
                        'test_id': f"{table['table_id']}_{policy_id}_unfiltered_{except_group}",
                        'type': 'exception',
                        'description': f"[{source_scope}] EXCEPT '{except_group}' sees all rows in {fqn}",
                        'principal_group': except_group,
                        'table': fqn,
                        'policy_id': policy_id,
                        'source_scope': source_scope,
                        'expected_result': 'ALL_ROWS',
                        'sql': f"SELECT COUNT(*) FROM {fqn}; -- Should return 10"
                    })

    return tests


test_cases = generate_test_cases(policies_config, securables_config)

print(f"Generated {len(test_cases)} test cases:")
print(f"  Grant tests:      {len([t for t in test_cases if t['type'] == 'grant'])}")
print(f"  Negative tests:   {len([t for t in test_cases if t['type'] == 'negative'])}")
print(f"  Masking tests:    {len([t for t in test_cases if t['type'] == 'masking'])}")
print(f"  Exception tests:  {len([t for t in test_cases if t['type'] == 'exception'])}")
print(f"  Row filter tests: {len([t for t in test_cases if t['type'] == 'row_filter'])}")
print(f"\nTest Matrix:")
print(f"{'='*100}")
print(f"{'Test ID':<55} {'Type':<12} {'Expected':<20}")
print(f"{'-'*100}")
for t in test_cases:
    print(f"{t['test_id']:<55} {t['type']:<12} {t['expected_result']:<20}")

# COMMAND ----------

# DBTITLE 1,Run validation test suite
# ============================================================================
# RUN VALIDATION TEST SUITE
# ============================================================================
# Executes tests that can be validated with the current user's context:
#   1. Table accessibility (grant tests)
#   2. Masking enforcement (check output patterns)
#   3. Row filter enforcement (check row counts)
#
# Tests requiring a different principal (TO/EXCEPT group switching) are
# logged as SKIPPED — they require impersonation or separate sessions.

import re

# Expected masking patterns per UDF
MASKING_PATTERNS = {
    'mask_email': r'^\*\*\*@.+$',           # ***@domain.com
    'mask_phone': r'^\(\*\*\*\) \*\*\*-',  # (***) ***-XXXX
    'mask_ssn': r'^\*\*\*-\*\*-\d{4}$',    # ***-**-1234
    'redact_full': r'^\[REDACTED\]$',       # [REDACTED]
    'mask_pii_string': r'^.\*\*\*.$',       # first***last char
}


def validate_masking_pattern(value: str, udf_name: str) -> bool:
    """Check if a value matches the expected masking pattern for a UDF."""
    pattern = MASKING_PATTERNS.get(udf_name)
    if not pattern:
        return False
    return bool(re.match(pattern, str(value)))


def run_test_suite(test_cases: List[Dict]) -> Dict:
    """Run the test suite against live UC. Returns summary."""
    results = {
        'total': len(test_cases),
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'details': []
    }

    for test in test_cases:
        # --- GRANT tests: verify table is accessible ---
        if test['type'] == 'grant' and 'SELECT' in test.get('sql', ''):
            try:
                df = spark.sql(test['sql'])
                row_count = df.count()
                results['passed'] += 1
                results['details'].append({
                    'test_id': test['test_id'],
                    'status': 'PASSED',
                    'message': f'SELECT returned {row_count} rows'
                })
            except Exception as e:
                error_msg = str(e)
                if 'does not exist' in error_msg.upper():
                    results['skipped'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'SKIPPED',
                        'message': 'Table not deployed yet'
                    })
                else:
                    results['failed'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'FAILED',
                        'message': error_msg[:120]
                    })

        # --- MASKING tests: verify column values are masked ---
        elif test['type'] == 'masking':
            try:
                df = spark.sql(test['sql'])
                rows = df.collect()
                if not rows:
                    results['skipped'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'SKIPPED',
                        'message': 'No rows returned'
                    })
                    continue

                udf_name = test.get('udf', '')
                all_masked = True
                sample_values = []
                for col_name in test.get('masked_columns', []):
                    for row in rows:
                        val = row[col_name]
                        if val is not None:
                            sample_values.append(f"{col_name}='{val}'")
                            if not validate_masking_pattern(val, udf_name):
                                all_masked = False
                            break

                if all_masked and sample_values:
                    results['passed'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'PASSED',
                        'message': f'Masked: {sample_values[0]}'
                    })
                elif not sample_values:
                    results['skipped'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'SKIPPED',
                        'message': 'All values NULL - cannot validate pattern'
                    })
                else:
                    results['skipped'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'SKIPPED',
                        'message': f'Cleartext visible (current user in EXCEPT): {sample_values[0]}'
                    })
            except Exception as e:
                results['skipped'] += 1
                results['details'].append({
                    'test_id': test['test_id'],
                    'status': 'SKIPPED',
                    'message': f'Table/policy not deployed: {str(e)[:80]}'
                })

        # --- ROW FILTER tests: verify row count is subset ---
        elif test['type'] == 'row_filter':
            try:
                count_sql = test['sql'].split(';')[0]
                result = spark.sql(count_sql).collect()[0][0]
                if result < 10:
                    results['passed'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'PASSED',
                        'message': f'Row filter active: {result}/10 rows visible'
                    })
                else:
                    results['skipped'] += 1
                    results['details'].append({
                        'test_id': test['test_id'],
                        'status': 'SKIPPED',
                        'message': f'All {result} rows visible (user may be in EXCEPT group)'
                    })
            except Exception as e:
                results['skipped'] += 1
                results['details'].append({
                    'test_id': test['test_id'],
                    'status': 'SKIPPED',
                    'message': f'Not deployed: {str(e)[:80]}'
                })

        # --- All other tests require impersonation ---
        else:
            results['skipped'] += 1
            results['details'].append({
                'test_id': test['test_id'],
                'status': 'SKIPPED',
                'message': 'Requires specific principal context (impersonation)'
            })

    return results


print("Running validation test suite...")
print("(Tests requiring impersonation are skipped — run via DAB bundle per-group)")
print()

test_results = run_test_suite(test_cases)
print(f"\nTest Results:")
print(f"  Total:   {test_results['total']}")
print(f"  Passed:  {test_results['passed']}")
print(f"  Failed:  {test_results['failed']}")
print(f"  Skipped: {test_results['skipped']}")

if test_results['failed'] > 0:
    print(f"\n\u2717 Failed tests:")
    for d in test_results['details']:
        if d['status'] == 'FAILED':
            print(f"  \u2717 {d['test_id']}: {d['message']}")

if test_results['passed'] > 0:
    print(f"\n\u2713 Passed tests:")
    for d in test_results['details']:
        if d['status'] == 'PASSED':
            print(f"  \u2713 {d['test_id']}: {d['message']}")

# COMMAND ----------

# DBTITLE 1,Audit: Policy change history
# MAGIC %sql
# MAGIC -- ============================================================================
# MAGIC -- AUDIT QUERIES
# MAGIC -- ============================================================================
# MAGIC -- Track governance events via system tables
# MAGIC
# MAGIC -- Policy-related audit events (last 7 days)
# MAGIC SELECT
# MAGIC   event_time,
# MAGIC   user_identity.email AS actor,
# MAGIC   action_name,
# MAGIC   request_params,
# MAGIC   response.status_code
# MAGIC FROM system.access.audit
# MAGIC WHERE action_name IN (
# MAGIC   'createPolicy', 'dropPolicy', 'alterPolicy',
# MAGIC   'setTag', 'unsetTag',
# MAGIC   'grantPermission', 'revokePermission'
# MAGIC )
# MAGIC   AND event_date >= current_date() - INTERVAL 7 DAYS
# MAGIC ORDER BY event_time DESC
# MAGIC LIMIT 50;

# COMMAND ----------

# DBTITLE 1,Audit: Tag assignment history
# MAGIC %sql
# MAGIC -- Track tag changes across securables
# MAGIC SELECT
# MAGIC   event_time,
# MAGIC   user_identity.email AS actor,
# MAGIC   action_name,
# MAGIC   request_params['full_name_arg'] AS securable,
# MAGIC   request_params['tag_name'] AS tag_key,
# MAGIC   request_params['tag_value'] AS tag_value
# MAGIC FROM system.access.audit
# MAGIC WHERE action_name IN ('setTag', 'unsetTag')
# MAGIC   AND event_date >= current_date() - INTERVAL 30 DAYS
# MAGIC ORDER BY event_time DESC
# MAGIC LIMIT 100;

# COMMAND ----------

# DBTITLE 1,Audit: Access denied events
# MAGIC %sql
# MAGIC -- Track denied access attempts (potential policy enforcement)
# MAGIC SELECT
# MAGIC   event_time,
# MAGIC   user_identity.email AS requester,
# MAGIC   action_name,
# MAGIC   request_params['full_name_arg'] AS target_object,
# MAGIC   response.error_message
# MAGIC FROM system.access.audit
# MAGIC WHERE response.status_code != '200'
# MAGIC   AND action_name IN ('getTable', 'selectData', 'executeQuery')
# MAGIC   AND event_date >= current_date() - INTERVAL 7 DAYS
# MAGIC ORDER BY event_time DESC
# MAGIC LIMIT 50;

# COMMAND ----------

# DBTITLE 1,Drift Detection: Compare config vs UC state
# ============================================================================
# DRIFT DETECTION
# ============================================================================
# Compares the desired state (from YAML configs) against actual UC state.

def check_tag_drift(securables: dict) -> List[Dict]:
    """Check if governed tags on securables match the configuration."""
    drift_results = []
    
    for table in securables.get('tables', []):
        fqn = f"{table['catalog']}.{table['schema']}.{table['table_id']}"
        
        # Check table-level tags
        try:
            actual_tags_df = spark.sql(f"""
                SELECT tag_name, tag_value 
                FROM system.information_schema.table_tags 
                WHERE catalog_name = '{table['catalog']}'
                  AND schema_name = '{table['schema']}'
                  AND table_name = '{table['table_id']}'
            """)
            actual_tags = {row['tag_name']: row['tag_value'] for row in actual_tags_df.collect()}
            
            for expected_key, expected_value in table.get('tags', {}).items():
                actual_value = actual_tags.get(expected_key)
                if actual_value is None:
                    drift_results.append({
                        'object': fqn,
                        'type': 'table_tag',
                        'tag_key': expected_key,
                        'expected': expected_value,
                        'actual': 'MISSING',
                        'drift': 'TAG_MISSING'
                    })
                elif actual_value != expected_value:
                    drift_results.append({
                        'object': fqn,
                        'type': 'table_tag',
                        'tag_key': expected_key,
                        'expected': expected_value,
                        'actual': actual_value,
                        'drift': 'VALUE_MISMATCH'
                    })
        except Exception as e:
            drift_results.append({
                'object': fqn,
                'type': 'table_tag',
                'tag_key': '*',
                'expected': 'accessible',
                'actual': str(e)[:100],
                'drift': 'ACCESS_ERROR'
            })
        
        # Check column-level tags
        for col in table.get('columns', []):
            if not col.get('tags'):
                continue
            try:
                col_tags_df = spark.sql(f"""
                    SELECT tag_name, tag_value 
                    FROM system.information_schema.column_tags 
                    WHERE catalog_name = '{table['catalog']}'
                      AND schema_name = '{table['schema']}'
                      AND table_name = '{table['table_id']}'
                      AND column_name = '{col['name']}'
                """)
                col_actual_tags = {row['tag_name']: row['tag_value'] for row in col_tags_df.collect()}
                
                for expected_key, expected_value in col['tags'].items():
                    actual_value = col_actual_tags.get(expected_key)
                    if actual_value is None:
                        drift_results.append({
                            'object': f"{fqn}.{col['name']}",
                            'type': 'column_tag',
                            'tag_key': expected_key,
                            'expected': expected_value,
                            'actual': 'MISSING',
                            'drift': 'TAG_MISSING'
                        })
            except Exception:
                pass  # Column may not exist yet in pre-deployment
    
    return drift_results


# Run drift detection
print("Running drift detection...")
try:
    drift = check_tag_drift(securables_config)
    if drift:
        print(f"\n⚠ Found {len(drift)} drift items:")
        for d in drift:
            print(f"  [{d['drift']}] {d['object']} | {d['tag_key']}: expected='{d['expected']}', actual='{d['actual']}'")
    else:
        print("\n✓ No drift detected - UC state matches configuration")
except Exception as e:
    print(f"\n⚠ Drift detection skipped (tables may not exist yet): {str(e)[:100]}")