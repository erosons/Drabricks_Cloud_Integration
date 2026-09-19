# Complete Auto-Discovery Guide

## Overview

The ABAC framework supports **two levels of auto-discovery** from Unity Catalog:

1. **Schema-Level**: Auto-discover **tables** when schema has policies but no tables listed
2. **Table-Level**: Auto-discover **columns** when table has masking policy with `information_schema: true`

Both work together to minimize YAML configuration while maintaining comprehensive governance.

---

## Level 1: Schema-Level Auto-Discovery (Tables)

### Pattern

**bronze_securables.yml:**
```yaml
schemas:
  - schema_id: hr
    catalog: general_use
    policy_bindings:
      - mnpi_row_filtering    # ✓ Non-empty: Apply to ALL tables
    tags:
      mnpi: ""
    # ✓ NO tables listed - auto-discover from Unity Catalog
```

### What Happens

**Notebook 01 (Load Manifest):**
```
Schema general_use.hr has policies but no tables listed
→ Auto-discovering from Unity Catalog

Query executed:
  SELECT table_name
  FROM general_use.information_schema.tables
  WHERE table_schema = 'hr' AND table_type = 'MANAGED'

Discovered 4 tables:
  ✓ employees (inherits mnpi_row_filtering + mnpi tag)
  ✓ payroll (inherits mnpi_row_filtering + mnpi tag)
  ✓ benefits (inherits mnpi_row_filtering + mnpi tag)
  ✓ contractors (inherits mnpi_row_filtering + mnpi tag)
```

**Notebook 04 (Create Policies):**
```sql
-- ONE policy for entire schema
CREATE OR REPLACE POLICY mnpi_row_filtering
ON SCHEMA general_use.hr
FOR ROW FILTER
USING (...);
```

**Result:**
- ✓ All 4 tables automatically filtered
- ✓ New tables added to hr schema automatically protected
- ✓ No YAML updates needed when tables change

---

## Level 2: Table-Level Auto-Discovery (Columns)

### Pattern

**bronze_securables.yml:**
```yaml
tables:
  - table_id: accounts_payable
    catalog: general_use
    schema: finance
    policy_bindings:
      - mnpi_column_masking
    information_schema: true    # ✓ Auto-discover ALL columns
    # ✓ NO columns listed - auto-discover from Unity Catalog
```

### What Happens

**Notebook 04 (Create Policies):**
```
Table general_use.finance.accounts_payable
→ Auto-discovering columns from information_schema

Query executed:
  SELECT column_name
  FROM general_use.information_schema.columns
  WHERE table_schema = 'finance'
    AND table_name = 'accounts_payable'
  ORDER BY ordinal_position

✓ Auto-discovered 12 columns from information_schema
  - invoice_id
  - vendor_name
  - amount
  - payment_date
  - account_number
  - routing_number
  - tax_id
  - address
  - phone
  - email
  - notes
  - created_at

Creating column masks:
  ALTER TABLE general_use.finance.accounts_payable
    ALTER COLUMN invoice_id SET MASK ...
  ALTER TABLE general_use.finance.accounts_payable
    ALTER COLUMN vendor_name SET MASK ...
  ... (12 total)
```

**Result:**
- ✓ ALL 12 columns automatically masked
- ✓ New columns added to table automatically masked
- ✓ No YAML updates needed when columns change

---

## Combined: Both Levels Together

### Ultimate Auto-Discovery Pattern

**bronze_securables.yml:**
```yaml
schemas:
  - schema_id: finance
    catalog: general_use
    policy_bindings:
      - mnpi_column_masking    # ✓ Schema-wide masking
    tags:
      mnpi: ""
      department: "finance"
    # ✓ NO tables listed - auto-discover
    # ✓ NO columns listed - auto-discover (via information_schema: true)
```

**What this achieves:**

1. **Auto-discover ALL tables** in finance schema from UC
2. **Each table inherits** `mnpi_column_masking` policy
3. **Auto-discover ALL columns** in each table from UC
4. **Mask every column** in every table

**One line in YAML:**
```yaml
policy_bindings: [mnpi_column_masking]
```

**Protects:**
- ✓ All existing tables
- ✓ All existing columns
- ✓ All future tables
- ✓ All future columns

**No enumeration needed!**

---

## Comparison: Explicit vs Auto-Discovery

### Example: Masking Finance Schema

#### Option A: Fully Explicit (Manual)
```yaml
schemas:
  - schema_id: finance
    policy_bindings: []    # Empty - check each table
    tables:
      - table_id: accounts_payable
        policy_bindings: [mnpi_column_masking]
        information_schema: false
        mnpi_masked_columns:
          - invoice_id
          - vendor_name
          - amount
          - payment_date
          - account_number
          - routing_number
          - tax_id
          - address
          - phone
          - email
          - notes
          - created_at
      
      - table_id: accounts_receivable
        policy_bindings: [mnpi_column_masking]
        information_schema: false
        mnpi_masked_columns:
          - customer_id
          - invoice_number
          - amount_due
          - payment_date
          - credit_card
          - bank_account
          # ... more columns
      
      # ... 10 more tables with 10-20 columns each
```

**Lines of YAML: ~500 lines**  
**Maintenance: High** - Must update when tables/columns change

---

#### Option B: Full Auto-Discovery (Recommended)
```yaml
schemas:
  - schema_id: finance
    policy_bindings:
      - mnpi_column_masking    # ✓ All tables + all columns
    tags:
      mnpi: ""
    # No tables listed - auto-discover
    # No columns listed - auto-discover (information_schema: true default)
```

**Lines of YAML: 5 lines**  
**Maintenance: Zero** - Automatically adapts to changes

---

## Configuration Options by Use Case

### Use Case 1: Entire Schema, All Columns

**Goal:** Mask all columns in all tables in finance schema

```yaml
schemas:
  - schema_id: finance
    policy_bindings:
      - mnpi_column_masking
    # Auto-discover: tables + columns
```

**Result:**
- Schema-level policy created
- All tables discovered → inherit policy
- All columns discovered → masked

---

### Use Case 2: Entire Schema, Specific Columns

**Goal:** Mask only salary-related columns across all tables

```yaml
schemas:
  - schema_id: hr
    policy_bindings: []        # Check each table
    # Auto-discover tables, then apply to each:
    # (This requires explicit table listing for column control)

# Alternative: Use column templates
# See HIERARCHICAL_POLICY_INHERITANCE.md
```

**Note:** For selective columns across many tables, use column templates (not covered here).

---

### Use Case 3: Specific Tables, All Columns

**Goal:** Mask all columns in accounts_payable, not other finance tables

```yaml
schemas:
  - schema_id: finance
    policy_bindings: []        # Empty - check tables
    tables:
      - table_id: accounts_payable
        policy_bindings: [mnpi_column_masking]
        information_schema: true    # ✓ Auto-discover columns
      
      - table_id: public_reports
        # No policies - not masked
```

**Result:**
- Table-level policy on accounts_payable only
- All columns in accounts_payable discovered and masked
- public_reports unaffected

---

### Use Case 4: Specific Tables, Specific Columns

**Goal:** Mask only salary, bonus, ssn in employees table

```yaml
tables:
  - table_id: employees
    schema: hr
    policy_bindings:
      - pii_column_masking
    information_schema: false    # ✓ Explicit columns
    mnpi_masked_columns:
      - salary
      - bonus
      - ssn
```

**Result:**
- Table-level policy on employees
- Only 3 columns masked (not auto-discovered)

---

## Auto-Discovery Decision Matrix

| Schema Policies | Tables Listed | information_schema | Columns Listed | Behavior |
|----------------|---------------|-------------------|----------------|----------|
| Yes (non-empty) | No | N/A | N/A | Auto-discover tables |
| Yes (non-empty) | Yes (explicit) | true | No | Use explicit tables, auto-discover columns |
| Yes (non-empty) | Yes (explicit) | false | Yes | Use explicit tables + columns |
| No (empty) | Yes (explicit) | true | No | Use explicit tables, auto-discover columns |
| No (empty) | Yes (explicit) | false | Yes | Use explicit tables + columns |

---

## Real-World Example

### Scenario: Growing Finance Department

**Year 1:**
```yaml
schemas:
  - schema_id: finance
    policy_bindings: [mnpi_column_masking]
```

**What's protected:**
- 5 tables with 50 total columns
- All automatically discovered and masked

**Year 2:**
- Added 10 new tables
- Added 30 new columns to existing tables

**YAML changes needed:** **ZERO**

**New protection:**
- 15 tables with 180 total columns
- All automatically discovered and masked
- No deployment needed (just run notebook 01-04 again)

---

## Verification Commands

### Check Auto-Discovered Tables

**After Notebook 01:**
```python
# Show tables discovered for schema
schema_name = "hr"
discovered = [
    t for t in manifest.tables 
    if t.schema == schema_name 
    and t.source_file.endswith("bronze_securables.yml")
]

print(f"Tables discovered in {schema_name}: {len(discovered)}")
for t in discovered:
    print(f"  - {t.table_id}")
    print(f"    Inherited policies: {t.inherited_policy_bindings}")
    print(f"    Tags: {t.tags}")
```

### Check Auto-Discovered Columns

**After Notebook 04:**
```python
# Show columns discovered for table
table_fqn = "general_use.finance.accounts_payable"

# Query what was discovered
cols = spark.sql(f"""
    SELECT column_name, data_type
    FROM general_use.information_schema.columns
    WHERE table_schema = 'finance'
      AND table_name = 'accounts_payable'
    ORDER BY ordinal_position
""").collect()

print(f"Columns in {table_fqn}: {len(cols)}")
for col in cols:
    print(f"  - {col.column_name} ({col.data_type})")

# Check if masks applied
spark.sql(f"DESCRIBE EXTENDED {table_fqn}").show(100, False)
```

---

## Troubleshooting

### Tables Not Discovered?

**Check:**
```sql
-- Verify tables exist in UC
SHOW TABLES IN general_use.hr;

-- Verify they are MANAGED
SELECT table_name, table_type
FROM general_use.information_schema.tables
WHERE table_schema = 'hr';
```

**Fix:**
- Ensure tables exist before running notebook 01
- Only MANAGED tables are discovered (not EXTERNAL or VIEW)
- Check Spark session has SELECT permission on information_schema

---

### Columns Not Discovered?

**Check:**
```sql
-- Verify columns exist
SELECT column_name, data_type
FROM general_use.information_schema.columns
WHERE table_schema = 'finance'
  AND table_name = 'accounts_payable';
```

**Fix:**
- Ensure `information_schema: true` is set in YAML
- Ensure table exists before running notebook 04
- Check Spark session has SELECT permission on information_schema

---

### Mix of Auto and Explicit

**Problem:** Some tables auto-discovered, others explicit

**Solution:** Use explicit table override:
```yaml
schemas:
  - schema_id: hr
    policy_bindings: [mnpi_row_filtering]    # Auto-discover most tables
    tables:
      - table_id: public_directory
        policy_bindings: []                   # Override: no policies
      # Other tables auto-discovered
```

---

## Best Practices

### ✓ Use Auto-Discovery When:
1. **Homogeneous data**: All tables/columns need same governance
2. **Dynamic schemas**: Tables/columns added frequently
3. **Large scale**: Many tables (10+) or columns (20+)
4. **Consistent rules**: Simple, uniform policies

### ✓ Use Explicit When:
1. **Heterogeneous data**: Different tables/columns need different policies
2. **Selective governance**: Some tables/columns excluded
3. **Compliance requirements**: Must document exact governed objects
4. **Complex rules**: Different policies per object

### ✓ Hybrid Approach (Recommended):
```yaml
schemas:
  - schema_id: finance
    policy_bindings: [standard_masking]    # Default for auto-discovered
    tables:
      - table_id: highly_sensitive
        policy_bindings: [enhanced_masking]  # Override
        information_schema: true             # But still auto-discover columns
      
      - table_id: public_data
        policy_bindings: []                  # Override: no policies
      
      # All other tables auto-discovered with standard_masking
```

---

## Summary

### Two-Level Auto-Discovery

```
Level 1: Schema → Tables
  ✓ No tables listed in YAML
  ✓ System queries information_schema.tables
  ✓ All tables discovered and inherit schema policies

Level 2: Table → Columns
  ✓ information_schema: true in YAML
  ✓ System queries information_schema.columns
  ✓ All columns discovered and masked

Combined: Schema-wide + Column-wide
  ✓ One policy definition in YAML
  ✓ Covers all tables + all columns
  ✓ Adapts automatically to changes
```

### Configuration Patterns

| Pattern | Tables | Columns | Config Lines | Auto-Adapts |
|---------|--------|---------|--------------|-------------|
| **Full Auto** | Auto | Auto | ~5 | Yes ✓ |
| **Schema + Column Auto** | Explicit | Auto | ~20 | Columns only |
| **Table + Column Auto** | Auto | Explicit | ~50 | Tables only |
| **Full Explicit** | Explicit | Explicit | ~500 | No |

**Recommendation:** Start with **Full Auto**, add explicit overrides only where needed.

---

## Your Configuration Examples

### Bronze Layer
```yaml
schemas:
  # Schema-wide row filtering (auto-discover tables)
  - schema_id: hr
    policy_bindings: [mnpi_row_filtering]
    tags: {mnpi: ""}
    # Tables auto-discovered from UC

  # Table-level column masking (explicit tables, auto-discover columns)
  - schema_id: finance
    policy_bindings: []
    tables:
      - table_id: accounts_payable
        policy_bindings: [mnpi_column_masking]
        information_schema: true    # All columns auto-discovered
      
      - table_id: cash_flow
        policy_bindings: [mnpi_column_masking]
        information_schema: false   # Explicit columns
        mnpi_masked_columns: [amount, credit_card, ...]
```

### Silver Layer
```yaml
schemas:
  - schema_id: employee_silver
    policy_bindings: []
    tables:
      - table_id: employees
        policy_bindings: [mnpi_column_masking]
        information_schema: false   # Explicit columns
        mnpi_masked_columns:
          - salary
          - bonus
          - stock_options
          # ... specific MNPI columns
```

**Deploy and run Notebook 01-04 to see auto-discovery in action!**
