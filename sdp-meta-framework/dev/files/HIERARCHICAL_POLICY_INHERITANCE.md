# Hierarchical Policy Inheritance Model

## Overview

The SDP-META ABAC framework now implements a **cascading policy inheritance model** across four scopes:

```
CATALOG scope
    ↓ inherits to
SCHEMA scope
    ↓ inherits to
TABLE scope
    ↓ applies to
COLUMN scope
```

## Inheritance Rules

### 1. Policy Cascade
- **Catalog-level policies** → inherited by ALL schemas and tables in that catalog
- **Schema-level policies** → inherited by ALL tables in that schema  
- **Table-level policies** → applied to the entire table
- **Column-level policies** → applied only to explicitly defined columns

### 2. Specificity Wins
More specific scope **overrides** broader scope:
- Table-level policies override schema-level
- Schema-level policies override catalog-level
- Explicit column definitions override table-level "all columns"

### 3. Tag Inheritance
Tags follow the same cascade:
- Catalog tags → inherited by all schemas/tables
- Schema tags → inherited by all tables  
- Table tags → apply to that table

## Configuration Examples

### Catalog-Level Policy (All tables inherit)

```yaml
catalogs:
  - catalog_id: general_use
    policy_bindings:
      - global_audit_filter    # Applies to ALL tables in catalog
    tags:
      compliance: "sox"         # All tables inherit this tag
```

### Schema-Level Policy (Tables in schema inherit)

```yaml
schemas:
  - schema_id: hr
    catalog: general_use
    policy_bindings:
      - mnpi_row_filtering     # ALL tables in hr schema get filtered
    tags:
      mnpi: ""                  # All hr tables inherit mnpi tag
    tables:
      - table_id: employees    # Inherits mnpi_row_filtering + mnpi tag
        # No need to redefine inherited policies
```

### Table-Level Policy (Override schema)

```yaml
schemas:
  - schema_id: finance
    catalog: general_use
    policy_bindings:
      - pii_masking            # Schema-level default
    tables:
      - table_id: cash_flow
        policy_bindings:
          - mnpi_column_masking  # Overrides schema default
          - custom_filter        # Additional table-specific policy
        information_schema: true  # Mask ALL columns
```

### Column-Level Policy (Specific columns only)

```yaml
tables:
  - table_id: employees
    schema: hr
    policy_bindings:
      - mnpi_column_masking
    information_schema: false
    mnpi_masked_columns:      # Only these columns masked
      - salary
      - bonus
      - ssn
```

## How It Works

### 1. Loading (Notebook 01)
```python
# Load governance from spec tables
manifest = loader.load()

# Apply inheritance (catalog → schema → table)
from policy_inheritance import apply_inheritance_to_manifest
manifest = apply_inheritance_to_manifest(manifest)

# Each table now has:
#   - policy_bindings: full list (direct + inherited)
#   - inherited_policy_bindings: what came from catalog/schema
#   - tags: merged (catalog + schema + table)
```

### 2. Tag Application (Notebook 02)
```python
# Apply table-level tags
ALTER TABLE {catalog}.{schema}.{table} SET TAGS ('mnpi' = '')

# Apply column-level tags (from templates)
ALTER TABLE {catalog}.{schema}.{table} 
  ALTER COLUMN salary SET TAGS ('pii' = '')
```

### 3. Policy Creation (Notebook 04)
Policies are created at their **original scope**:

```sql
-- Catalog-level (defined at catalog)
CREATE OR REPLACE POLICY global_audit 
ON CATALOG general_use 
FOR ROW FILTER ...

-- Schema-level (defined at schema)
CREATE OR REPLACE POLICY mnpi_row_filter
ON SCHEMA general_use.hr
FOR ROW FILTER ...

-- Table-level (defined at table)
CREATE OR REPLACE POLICY custom_mask
ON TABLE general_use.finance.cash_flow
FOR COLUMN MASKING ...
```

**Key**: Inherited policies are NOT recreated at lower scopes. The engine only creates policies at their original definition scope.

## Masking Scope Behavior

### information_schema: true
**Mask ALL columns** in the table:
```yaml
- table_id: accounts_payable
  policy_bindings:
    - mnpi_column_masking
  information_schema: true   # Queries information_schema for all columns
```

### information_schema: false
**Mask ONLY specified columns**:
```yaml
- table_id: cash_flow
  policy_bindings:
    - mnpi_column_masking
  information_schema: false
  mnpi_masked_columns:       # MUST specify columns
    - amount
    - credit_card
```

### No explicit columns + inherited masking policy
**Mask ALL columns** (inherited policy applies to whole table):
```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - pii_masking           # Schema-level masking
    tables:
      - table_id: employees   # No explicit columns → ALL columns masked
```

## Benefits

### 1. Reduced Configuration
Define once at catalog/schema level, applies to all tables:
```yaml
# Instead of 100 table definitions with same policy
schemas:
  - schema_id: finance
    policy_bindings:
      - mnpi_column_masking   # All 100 tables inherit
```

### 2. Consistency
All tables in a domain get same governance automatically:
- All HR tables filtered by department
- All finance tables masked for MNPI
- All production catalogs audited

### 3. Flexibility
Override at lower scope when needed:
```yaml
schemas:
  - schema_id: finance
    policy_bindings:
      - standard_masking      # Default for schema
    tables:
      - table_id: sensitive_deals
        policy_bindings:
          - enhanced_masking   # Override for this table
```

### 4. Clear Visibility
Display shows inherited vs direct policies:
```
table_id  | policy_bindings      | inherited_policies
----------|---------------------|--------------------
employees | custom_filter       | [mnpi_row_filtering]
cash_flow | mnpi_column_masking | []
```

## Implementation Components

### New Files
1. **`policy_inheritance.py`** - Inheritance engine
   - `PolicyInheritanceEngine` class
   - `apply_inheritance_to_manifest()` function
   - Scope resolution logic

### Updated Files
1. **`spec_table_reader.py`** - Load catalogs and schemas
   - Returns `(catalogs, schemas, tables)` tuple
   - Extracts schema-level configs

2. **`config_loader.py`** - Added `tags` field to `ResolvedTable`

3. **Notebook 01** - Apply inheritance after loading
4. **Notebook 02** - Apply table-level tags
5. **Notebook 04** - Only create policies at original scope

## Execution Order

```
1. Notebook 01: Load from spec tables
   ├─ Load bronze_securables.yml
   ├─ Load silver_securables.yml
   ├─ Extract catalogs, schemas, tables
   └─ Apply inheritance engine
       ├─ Catalog policies → schemas
       ├─ Catalog/schema policies → tables
       └─ Merge with table-specific

2. Notebook 02: Apply tags
   ├─ Table-level tags
   └─ Column-level tags (from templates)

3. Notebook 03: Deploy UDFs

4. Notebook 03b: Grant RBAC

5. Notebook 04: Create policies
   ├─ Catalog-level: CREATE POLICY ON CATALOG
   ├─ Schema-level: CREATE POLICY ON SCHEMA
   └─ Table-level: CREATE POLICY ON TABLE

6. Notebook 05: Validate enforcement

7. Notebook 06: Drift detection
```

## Migration Path

### From Flat (No Inheritance)
**Before:**
```yaml
tables:
  - table_id: employees
    policy_bindings: [mnpi_row_filtering, pii_masking]
  - table_id: payroll
    policy_bindings: [mnpi_row_filtering, pii_masking]
  - table_id: benefits
    policy_bindings: [mnpi_row_filtering, pii_masking]
```

**After:**
```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - mnpi_row_filtering
      - pii_masking
    tables:
      - table_id: employees
      - table_id: payroll
      - table_id: benefits
        # All inherit schema policies automatically
```

### Adding Exceptions
```yaml
schemas:
  - schema_id: hr
    policy_bindings:
      - mnpi_row_filtering    # Default for all tables
    tables:
      - table_id: public_directory
        policy_bindings: []    # Override: no filtering for this table
```

## Troubleshooting

### Policy not inherited?
Check notebook 01 output - inheritance resolution should show:
```
✓ Policy inheritance resolved:
  Table: employees
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
```

### Duplicate policies created?
Check notebook 04 - should only create at original scope:
```
CATALOG: 2 bindings
SCHEMA: 5 bindings  
TABLE: 12 bindings (only direct, not inherited)
```

### Tags not appearing?
Run notebook 02 after notebook 01 to apply both:
- Table-level tags (from YAML `tags:`)
- Column-level tags (from templates)
