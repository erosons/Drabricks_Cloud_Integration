# Schema-Wide Governance Pattern

## Overview

For schemas where **ALL tables should have the same governance**, you can define policies at the schema level without listing individual tables. The system will:

1. **Create policy ON SCHEMA** (one policy for entire schema)
2. **Auto-discover all tables** from Unity Catalog `information_schema`
3. **Apply inherited policies** to all discovered tables
4. **Automatically cover new tables** added to schema later

This is the **schema-wide governance pattern** - perfect for:
- Departmental schemas where all data has same sensitivity
- Schemas with many tables (don't want to enumerate all)
- Dynamic schemas where tables are added/removed frequently

---

## Configuration Pattern

### Schema-Wide Policy (Auto-Discovery)

**bronze_securables.yml:**
```yaml
schemas:
  - schema_id: hr
    catalog: general_use
    policy_bindings:
      - mnpi_row_filtering      # ✓ Non-empty: Apply to ALL tables
    tags:
      mnpi: ""                   # ✓ All tables inherit this tag
    grants:
      - group: hr_data_readers
        privileges: [USE SCHEMA, SELECT]
    # ✓ NO tables section - system auto-discovers from Unity Catalog
```

**What happens:**

1. **At deployment time (Notebook 01):**
   ```sql
   -- System queries Unity Catalog
   SELECT table_name 
   FROM general_use.information_schema.tables
   WHERE table_schema = 'hr'
   ```

2. **Discovered tables added to manifest:**
   ```
   Tables discovered in general_use.hr:
     - employees (inherits mnpi_row_filtering + mnpi tag)
     - payroll (inherits mnpi_row_filtering + mnpi tag)
     - benefits (inherits mnpi_row_filtering + mnpi tag)
     - contractors (inherits mnpi_row_filtering + mnpi tag)
   ```

3. **Policy created once (Notebook 04):**
   ```sql
   CREATE OR REPLACE POLICY mnpi_row_filtering
   ON SCHEMA general_use.hr
   FOR ROW FILTER
   USING (general_use.platform_admin.filter_mnpi_access('hr_mnpi_approved'));
   ```

**Result:**
- ✓ ONE policy covers all tables
- ✓ No need to enumerate tables in YAML
- ✓ New tables automatically protected
- ✓ Consistent governance across entire schema

---

## Comparison: Schema-Wide vs Table-Level

### Pattern 1: Schema-Wide (Auto-Discovery)

**Use when:**
- All tables in schema need same governance
- Schema has many tables
- Tables are added/removed dynamically
- Want simple, consistent rules

**Configuration:**
```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - mnpi_row_filtering    # Non-empty
    # No tables listed
```

**Result:**
- Policy scope: `ON SCHEMA`
- Tables: Auto-discovered from UC
- Policy count: 1 (for entire schema)
- New tables: Automatically covered

---

### Pattern 2: Table-Level (Explicit)

**Use when:**
- Different tables need different policies
- Fine-grained control required
- Some tables excluded from governance
- Mix of row filtering and column masking

**Configuration:**
```yaml
schemas:
  - schema_id: finance
    policy_bindings: []       # Empty
    tables:
      - table_id: accounts_payable
        policy_bindings:
          - mnpi_column_masking
      - table_id: cash_flow
        policy_bindings:
          - mnpi_column_masking
      - table_id: public_reports
        policy_bindings: []   # No governance
```

**Result:**
- Policy scope: `ON TABLE`
- Tables: Explicitly listed
- Policy count: 2 (one per table with policies)
- New tables: Must be added to YAML

---

## Complete Example

### Scenario: Multi-Department Organization

**bronze_securables.yml:**
```yaml
catalogs:
  - catalog_id: general_use
    policy_bindings: []

schemas:
  # HR: Schema-wide governance (all tables same policy)
  - schema_id: hr
    catalog: general_use
    policy_bindings:
      - mnpi_row_filtering      # ALL hr tables
    tags:
      mnpi: ""
      department: "hr"
    # No tables listed - auto-discover

  # Finance: Mixed governance (tables have different policies)
  - schema_id: finance
    catalog: general_use
    policy_bindings: []          # Empty - check each table
    tags:
      department: "finance"
    tables:
      - table_id: sensitive_deals
        policy_bindings:
          - mnpi_row_filtering
          - mnpi_column_masking
        tags:
          mnpi: ""
          sensitivity: "high"

      - table_id: public_reports
        policy_bindings: []      # No policies
        tags:
          sensitivity: "public"

  # Analytics: Schema-wide (all tables masked)
  - schema_id: customer_analytics
    catalog: general_use
    policy_bindings:
      - pii_column_masking       # ALL analytics tables
    tags:
      pii: ""
    # No tables listed - auto-discover
```

### Expected Behavior

**Notebook 01 Output:**
```
Loading bronze governance from: .../bronze_securables.yml

Schema general_use.hr has policies but no tables listed - auto-discovering from Unity Catalog
  Discovered 15 tables in general_use.hr
    ✓ employees (inherits mnpi_row_filtering)
    ✓ payroll (inherits mnpi_row_filtering)
    ✓ benefits (inherits mnpi_row_filtering)
    ... (12 more)

Schema general_use.finance has empty policy_bindings → check table-level
  ✓ sensitive_deals (explicit policies)
  ✓ public_reports (no policies)

Schema general_use.customer_analytics has policies but no tables listed - auto-discovering
  Discovered 8 tables in general_use.customer_analytics
    ✓ customer_profiles (inherits pii_column_masking)
    ✓ purchase_history (inherits pii_column_masking)
    ... (6 more)

✓ Loaded: 3 schemas, 25 tables (23 auto-discovered, 2 explicit)

✓ Policy inheritance resolved:
  TWO-TIER SCOPING MODEL:
    Schemas with policies (ON SCHEMA): 2
      ↑ hr, customer_analytics (auto-discovery)
    
    Schemas delegating to tables: 1
      ↑ finance (explicit tables)
    
    Tables with inherited policies: 23
      ↑ All discovered tables from hr and customer_analytics
    
    Tables with direct policies (ON TABLE): 1
      ↑ finance.sensitive_deals
```

**Notebook 04 Output:**
```
Creating policies:

SCHEMA-level (schema-wide governance):
  ✓ CREATE POLICY mnpi_row_filtering ON SCHEMA general_use.hr
    Covers: 15 tables (all tables in hr)

  ✓ CREATE POLICY pii_column_masking ON SCHEMA general_use.customer_analytics
    Covers: 8 tables (all tables in customer_analytics)

TABLE-level (explicit governance):
  ✓ CREATE POLICY mnpi_row_filtering ON TABLE general_use.finance.sensitive_deals
  ✓ CREATE POLICY mnpi_column_masking ON TABLE general_use.finance.sensitive_deals

Total: 2 schema-level policies + 2 table-level policies = 4 policies
  Coverage: 25 tables governed
```

---

## Auto-Discovery Details

### What Tables Are Discovered?

Query executed for each schema with non-empty `policy_bindings`:

```sql
SELECT table_name
FROM {catalog}.information_schema.tables
WHERE table_schema = '{schema_id}'
  AND table_type = 'MANAGED'
ORDER BY table_name
```

Only **MANAGED** tables are discovered (not EXTERNAL or VIEW by default).

### Discovered Table Properties

Each auto-discovered table inherits:

```yaml
table_id: <discovered_name>
catalog: <from schema>
schema: <from schema>
description: "Auto-discovered from <catalog>.<schema> (inherits schema policies)"
policy_bindings: []                    # Empty - inherits from schema
tags: <schema.tags>                    # Inherits schema-level tags
grants: []                             # Schema grants apply
```

### When Auto-Discovery Runs

Auto-discovery happens:
- **When:** Notebook 01 loads manifest
- **Trigger:** Schema has `policy_bindings: [...]` (non-empty) AND no `tables:` section
- **Frequency:** Every time notebook 01 runs (dynamic)

This means:
- ✓ New tables added to schema are automatically discovered
- ✓ Deleted tables are automatically removed
- ✓ No YAML updates needed when tables change

---

## Overriding Inherited Policies

If a specific table needs different governance than the schema-wide policy:

### Option 1: Define Table Explicitly with Override

```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - mnpi_row_filtering      # Default for ALL hr tables
    tables:
      - table_id: public_directory
        policy_bindings: []      # Override: NO policies for this table
        
      - table_id: executives
        policy_bindings:
          - enhanced_mnpi_filtering  # Override: Stricter policy
```

**Result:**
- Most hr tables: Inherit `mnpi_row_filtering` (auto-discovered)
- `public_directory`: No policies (explicit override)
- `executives`: Uses `enhanced_mnpi_filtering` (explicit override)

### Option 2: Move Schema to Table-Level Delegation

```yaml
schemas:
  - schema_id: hr
    policy_bindings: []          # Empty - delegate to tables
    tables:
      - table_id: employees
        policy_bindings: [mnpi_row_filtering]
      - table_id: payroll
        policy_bindings: [mnpi_row_filtering]
      - table_id: public_directory
        policy_bindings: []      # No policies
```

**Trade-off:**
- ✓ Fine-grained control
- ✗ Must enumerate all tables
- ✗ New tables not automatically governed

---

## Disabling Auto-Discovery

To disable auto-discovery (use only explicit tables):

**Notebook 01:**
```python
loader = SpecTableABACLoader(
    spark=spark,
    catalog=catalog,
    sdp_meta_schema=sdp_meta_schema,
    bronze_spec_table=bronze_spec_table,
    silver_spec_table=silver_spec_table,
    policies_path=policies_path,
    auto_discover_tables=False    # Disable auto-discovery
)
```

With auto-discovery disabled:
- Schema with policies but no tables → Warning logged, no tables loaded
- Only explicitly listed tables are governed

---

## Best Practices

### ✓ Use Schema-Wide When:
1. **Homogeneous schemas**: All tables have same sensitivity
   - HR department data
   - Finance department data
   - Customer PII data

2. **Dynamic schemas**: Tables added/removed frequently
   - Staging schemas
   - User-generated tables
   - Pipeline output schemas

3. **Large schemas**: Many tables (10+)
   - Don't want to enumerate all in YAML
   - Consistent governance more important than per-table control

### ✓ Use Table-Level When:
1. **Heterogeneous schemas**: Tables have different sensitivity
   - Mixed public and private data
   - Different regulatory requirements

2. **Selective governance**: Not all tables need governance
   - Some tables are public
   - Some tables are temporary/scratch

3. **Complex policies**: Different tables need different policy combinations
   - Some row filtering only
   - Some column masking only
   - Some both

### ✓ Mixed Approach:
Schema-wide as default + table-level overrides:

```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - mnpi_row_filtering      # Default for most tables
    tables:
      - table_id: public_directory
        policy_bindings: []      # Override: public data
      # All other hr tables auto-discovered and inherit
```

---

## Troubleshooting

### Tables Not Discovered?

**Check:**
1. Tables exist in Unity Catalog
   ```sql
   SHOW TABLES IN general_use.hr;
   ```

2. Tables are MANAGED (not EXTERNAL)
   ```sql
   DESCRIBE TABLE EXTENDED general_use.hr.employees;
   ```

3. Spark session has permissions
   ```sql
   SELECT * FROM general_use.information_schema.tables
   WHERE table_schema = 'hr';
   ```

### Schema Policy Not Applied?

**Verify:**
1. Schema has non-empty `policy_bindings`
   ```yaml
   policy_bindings:
     - some_policy    # Must be non-empty
   ```

2. No `tables:` section under schema
   ```yaml
   # This triggers auto-discovery:
   - schema_id: hr
     policy_bindings: [...]
     # NO tables: section here
   ```

3. Check notebook 01 logs for discovery messages

---

## Summary

**Schema-Wide Governance = Set and Forget**

✅ Define policy once at schema level  
✅ All tables automatically inherit  
✅ New tables automatically covered  
✅ Simple, consistent governance  
✅ Scales to large schemas  

**Perfect for your use case where you want:**
```yaml
schema_id: hr
policy_bindings:
  - mnpi_row_filtering    # ✓ All hr tables get this
# No tables listed           # ✓ System auto-discovers them
```

Deploy and run Notebook 01 to see auto-discovery in action!
