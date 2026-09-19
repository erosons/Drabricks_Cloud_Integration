# Two-Tier Scoping Model - Detailed Examples

## Overview

The ABAC framework implements a **two-tier scoping model** where the behavior depends on whether a schema has policies defined:

```
Schema has policy_bindings (non-empty)
   → Policy created ON SCHEMA
   → Covers ALL tables in that schema
   → No per-table policy creation needed

Schema has policy_bindings: [] (empty)
   → Engine checks EACH table for its own policy_bindings
   → Policies created ON TABLE (per-table basis)
   → Tables can have different policies
```

## Example 1: Schema-Level Policy (Non-Empty)

### Configuration

**bronze_securables.yml:**
```yaml
schemas:
  - schema_id: hr
    catalog: general_use
    policy_bindings:
      - mnpi_row_filtering      # NON-EMPTY: All tables inherit
    tags:
      mnpi: ""
    
    tables:
      - table_id: employees
        description: "Employee records"
        # No policy_bindings specified
        
      - table_id: payroll
        description: "Payroll records"
        # No policy_bindings specified
        
      - table_id: benefits
        description: "Benefits enrollment"
        # No policy_bindings specified
```

### After Inheritance (Notebook 01)

```
Schema: general_use.hr
  Policy bindings: [mnpi_row_filtering]
  Delegation mode: ON SCHEMA

Table: general_use.hr.employees
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
  Effective scope: SCHEMA

Table: general_use.hr.payroll
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
  Effective scope: SCHEMA

Table: general_use.hr.benefits
  Direct policies: []
  Inherited policies: [mnpi_row_filtering]
  Effective scope: SCHEMA
```

### Policy Creation (Notebook 04)

**ONE policy for entire schema:**
```sql
-- Created at SCHEMA level
CREATE OR REPLACE POLICY mnpi_row_filtering
ON SCHEMA general_use.hr
FOR ROW FILTER
USING (general_use.platform_admin.filter_mnpi_access('hr_mnpi_approved'));

-- Result: ALL tables in hr schema are filtered
--   - general_use.hr.employees  ✓ filtered
--   - general_use.hr.payroll    ✓ filtered
--   - general_use.hr.benefits   ✓ filtered
```

**Benefits:**
- ✓ Define once, applies to all tables
- ✓ No need to enumerate each table
- ✓ New tables automatically inherit policy
- ✓ Consistent governance across entire schema

---

## Example 2: Schema Delegates to Tables (Empty)

### Configuration

**bronze_securables.yml:**
```yaml
schemas:
  - schema_id: finance
    catalog: general_use
    policy_bindings: []         # EMPTY: Check each table
    
    tables:
      - table_id: accounts_payable
        description: "AP transactions"
        policy_bindings:
          - mnpi_column_masking   # Table-specific policy
        tags:
          mnpi: ""
        information_schema: true  # Mask all columns
        
      - table_id: cash_flow
        description: "Cash flow records"
        policy_bindings:
          - mnpi_column_masking   # Table-specific policy
        tags:
          mnpi: ""
        information_schema: false
        mnpi_masked_columns:
          - amount
          - credit_card
          
      - table_id: accounts_receivable
        description: "AR transactions"
        policy_bindings:
          - mnpi_row_filtering    # Different policy!
        tags:
          mnpi: ""
```

### After Inheritance (Notebook 01)

```
Schema: general_use.finance
  Policy bindings: []
  Delegation mode: CHECK EACH TABLE

Table: general_use.finance.accounts_payable
  Direct policies: [mnpi_column_masking]
  Inherited policies: []
  Effective scope: TABLE

Table: general_use.finance.cash_flow
  Direct policies: [mnpi_column_masking]
  Inherited policies: []
  Effective scope: TABLE

Table: general_use.finance.accounts_receivable
  Direct policies: [mnpi_row_filtering]
  Inherited policies: []
  Effective scope: TABLE
```

### Policy Creation (Notebook 04)

**Separate policies for EACH table:**
```sql
-- Created at TABLE level for accounts_payable
CREATE OR REPLACE POLICY mnpi_column_masking
ON TABLE general_use.finance.accounts_payable
FOR COLUMN MASKING
USING (general_use.platform_admin.mask_mnpi_value('finance_mnpi_approved', value));

-- Created at TABLE level for cash_flow
CREATE OR REPLACE POLICY mnpi_column_masking
ON TABLE general_use.finance.cash_flow
FOR COLUMN MASKING
USING (general_use.platform_admin.mask_mnpi_value('finance_mnpi_approved', value));

-- Created at TABLE level for accounts_receivable (DIFFERENT policy)
CREATE OR REPLACE POLICY mnpi_row_filtering
ON TABLE general_use.finance.accounts_receivable
FOR ROW FILTER
USING (general_use.platform_admin.filter_mnpi_access('finance_mnpi_approved'));
```

**Benefits:**
- ✓ Fine-grained control per table
- ✓ Different tables can have different policies
- ✓ Mix row filtering and column masking in same schema
- ✓ Explicit control over which tables have policies

---

## Example 3: Mixed - Schema Policy + Table Override

### Configuration

**bronze_securables.yml:**
```yaml
schemas:
  - schema_id: marketing
    catalog: general_use
    policy_bindings:
      - standard_pii_masking    # Default for schema
    
    tables:
      - table_id: campaigns
        # Inherits standard_pii_masking
        
      - table_id: customer_segments
        # Inherits standard_pii_masking
        
      - table_id: sensitive_deals
        # Override: different policy
        policy_bindings:
          - enhanced_pii_masking
          - mnpi_row_filtering
```

### After Inheritance (Notebook 01)

```
Schema: general_use.marketing
  Policy bindings: [standard_pii_masking]
  Delegation mode: ON SCHEMA (with overrides)

Table: general_use.marketing.campaigns
  Direct policies: []
  Inherited policies: [standard_pii_masking]
  Effective scope: SCHEMA

Table: general_use.marketing.customer_segments
  Direct policies: []
  Inherited policies: [standard_pii_masking]
  Effective scope: SCHEMA

Table: general_use.marketing.sensitive_deals
  Direct policies: [enhanced_pii_masking, mnpi_row_filtering]
  Inherited policies: []
  Effective scope: TABLE (OVERRIDE)
```

### Policy Creation (Notebook 04)

```sql
-- Schema-level policy for campaigns and customer_segments
CREATE OR REPLACE POLICY standard_pii_masking
ON SCHEMA general_use.marketing
FOR COLUMN MASKING
USING (...);

-- Table-level override for sensitive_deals
CREATE OR REPLACE POLICY enhanced_pii_masking
ON TABLE general_use.marketing.sensitive_deals
FOR COLUMN MASKING
USING (...);

CREATE OR REPLACE POLICY mnpi_row_filtering
ON TABLE general_use.marketing.sensitive_deals
FOR ROW FILTER
USING (...);
```

**Result:**
- `campaigns`: Uses schema-level `standard_pii_masking`
- `customer_segments`: Uses schema-level `standard_pii_masking`
- `sensitive_deals`: Uses table-level `enhanced_pii_masking` + `mnpi_row_filtering` (does NOT inherit schema policy)

---

## Example 4: Catalog-Level Inheritance

### Configuration

**bronze_securables.yml:**
```yaml
catalogs:
  - catalog_id: general_use
    policy_bindings:
      - global_audit_filter    # ALL schemas/tables inherit
    tags:
      compliance: "sox"

schemas:
  - schema_id: hr
    catalog: general_use
    policy_bindings: []        # Empty: check tables
    
    tables:
      - table_id: employees
        policy_bindings:
          - mnpi_column_masking  # Table-specific
```

### After Inheritance (Notebook 01)

```
Catalog: general_use
  Policy bindings: [global_audit_filter]

Schema: general_use.hr
  Policy bindings: []
  Delegation mode: CHECK EACH TABLE

Table: general_use.hr.employees
  Direct policies: [mnpi_column_masking]
  Inherited policies: [global_audit_filter]    # From catalog
  Tags: {compliance: "sox", ...}
  Effective scopes:
    - global_audit_filter: CATALOG
    - mnpi_column_masking: TABLE
```

### Policy Creation (Notebook 04)

```sql
-- Catalog-level policy (inherited by ALL)
CREATE OR REPLACE POLICY global_audit_filter
ON CATALOG general_use
FOR ROW FILTER
USING (...);

-- Table-level policy (specific to employees)
CREATE OR REPLACE POLICY mnpi_column_masking
ON TABLE general_use.hr.employees
FOR COLUMN MASKING
USING (...);
```

**Result:**
- `global_audit_filter` applies to ALL tables in `general_use` catalog (catalog-level)
- `mnpi_column_masking` applies only to `general_use.hr.employees` (table-level)

---

## Decision Tree: Where is Policy Created?

```
Is policy defined at CATALOG level?
├─ YES → CREATE POLICY ON CATALOG catalog_name
│         (All schemas and tables inherit)
│
└─ NO → Is policy defined at SCHEMA level?
        └─ Schema has policy_bindings (non-empty)?
           ├─ YES → CREATE POLICY ON SCHEMA catalog.schema
           │         (All tables in schema inherit)
           │
           └─ NO (empty) → Is policy defined at TABLE level?
                          ├─ YES → CREATE POLICY ON TABLE catalog.schema.table
                          │         (Only this table affected)
                          │
                          └─ NO → No policy created
```

---

## Verification in Notebook 01

After running notebook 01, check the output:

```
✓ Policy inheritance resolved:
  TWO-TIER SCOPING MODEL:
    Schemas with policies (ON SCHEMA): 2
      ↑ These schemas have non-empty policy_bindings
      ↑ Policies created ON SCHEMA, apply to all tables
    
    Schemas delegating to tables (empty policy_bindings): 3
      ↑ These schemas have policy_bindings: []
      ↑ Engine checks each table for its own policies
    
    Tables with inherited policies: 45
      ↑ These tables inherit from catalog or schema
      ↑ Policies created at higher scope
    
    Tables with direct policies (ON TABLE): 12
      ↑ These tables have their own policy_bindings
      ↑ Policies created ON TABLE
```

---

## Key Takeaways

### ✓ Schema with Policies (Non-Empty)
```yaml
policy_bindings:
  - some_policy    # Non-empty
```
- **ONE** policy created `ON SCHEMA`
- Covers **ALL** tables in schema
- No per-table enumeration
- New tables automatically protected

### ✓ Schema Delegates to Tables (Empty)
```yaml
policy_bindings: []  # Empty
```
- Engine checks **EACH** table
- Policies created `ON TABLE`
- Tables can have different policies
- Fine-grained control

### ✓ Table Override
When table specifies its own `policy_bindings`:
- Table's policies **REPLACE** inherited schema policies
- No merge with schema-level
- Full control at table scope

### ✓ Best Practices

**Use schema-level when:**
- All tables need same governance
- Simple, consistent rules
- Want automatic protection for new tables

**Use table-level when:**
- Different tables need different policies
- Fine-grained control required
- Mix of row filtering and column masking

**Use catalog-level when:**
- Organization-wide audit requirements
- Global compliance rules
- Cross-schema governance
