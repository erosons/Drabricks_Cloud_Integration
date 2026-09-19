# Securables Files Alignment Validation

## Files Validated
- `/conf/abac/bronze_securables.yml` (Bronze layer)
- `/conf/abac/silver_securables.yml` (Silver layer)

## Alignment Status: ✅ FIXED

---

## Structure Comparison

### bronze_securables.yml (Bronze Layer)

```yaml
api_version: governance.databricks.com/v2
kind: SecurableRegistry
metadata:
  registry_id: sdp_meta_bronze_securables

# CATALOGS
catalogs:
  - catalog_id: general_use
    policy_bindings: []              # ✅ Consistent with silver

# SCHEMAS
schemas:
  - schema_id: hr
    policy_bindings: []              # ✅ Empty → check tables
    tables:
      - table_id: employees          # ✅ Table added
        policy_bindings: [mnpi_row_filtering]

  - schema_id: finance
    policy_bindings: []              # ✅ Empty → check tables
    tables:
      - table_id: accounts_payable
        policy_bindings: [mnpi_column_masking]
      - table_id: cash_flow
        policy_bindings: [mnpi_column_masking]
      - table_id: accounts_receivable
        policy_bindings: [mnpi_row_filtering]
```

### silver_securables.yml (Silver Layer)

```yaml
api_version: governance.databricks.com/v2
kind: SecurableRegistry
metadata:
  registry_id: sdp_meta_silver_securables

# CATALOGS
catalogs:
  - catalog_id: general_use
    policy_bindings: []              # ✅ Consistent with bronze

# SCHEMAS
schemas:
  - schema_id: employee_silver
    policy_bindings: []              # ✅ Empty → check tables
    tables:
      - table_id: employees          # ✅ Has tables
        policy_bindings: [mnpi_column_masking]
```

---

## Fixes Applied

### ✅ Fix 1: Added catalogs section to bronze
**Before:**
```yaml
# No catalogs section
schemas:
  - schema_id: hr
```

**After:**
```yaml
catalogs:
  - catalog_id: general_use
    policy_bindings: []
    grants: [...]

schemas:
  - schema_id: hr
```

**Impact:** Bronze and silver now have consistent catalog definitions.

---

### ✅ Fix 2: Added tables to hr schema
**Before:**
```yaml
- schema_id: hr
  policy_bindings:
    - mnpi_row_filtering    # Policy defined but NO tables
  # NO TABLES LISTED
```

**Problem:** Policy would be created ON SCHEMA but apply to zero tables.

**After:**
```yaml
- schema_id: hr
  policy_bindings: []       # Changed to empty → check tables
  tables:
    - table_id: employees   # Added table
      policy_bindings:
        - mnpi_row_filtering
```

**Impact:** 
- hr.employees table now has proper governance
- Policy created ON TABLE (not wasted ON SCHEMA)
- Aligns with two-tier scoping model

---

## Validation Checklist

### ✅ Structure Consistency
- [x] Both files have `catalogs` section
- [x] Both files have `schemas` section
- [x] Both files have `tables` under schemas
- [x] Consistent YAML structure (api_version, kind, metadata)

### ✅ Two-Tier Scoping Compliance
- [x] Bronze hr: `policy_bindings: []` → checks tables ✓
- [x] Bronze finance: `policy_bindings: []` → checks tables ✓
- [x] Silver employee_silver: `policy_bindings: []` → checks tables ✓
- [x] All schemas with empty bindings have tables listed ✓

### ✅ Schema Definitions
| Schema | Layer | policy_bindings | Tables | Status |
|--------|-------|----------------|--------|--------|
| hr | Bronze | [] (empty) | 1 | ✓ Tables listed |
| finance | Bronze | [] (empty) | 3 | ✓ Tables listed |
| employee_silver | Silver | [] (empty) | 1 | ✓ Tables listed |

### ✅ Table Definitions
| Table | Layer | Schema | policy_bindings | Status |
|-------|-------|--------|----------------|--------|
| employees | Bronze | hr | [mnpi_row_filtering] | ✓ Valid |
| accounts_payable | Bronze | finance | [mnpi_column_masking] | ✓ Valid |
| cash_flow | Bronze | finance | [mnpi_column_masking] | ✓ Valid |
| accounts_receivable | Bronze | finance | [mnpi_row_filtering] | ✓ Valid |
| employees | Silver | employee_silver | [mnpi_column_masking] | ✓ Valid |

### ✅ Policy References
All referenced policies exist in `policies.yml`:
- [x] `mnpi_row_filtering` ✓
- [x] `mnpi_column_masking` ✓

### ✅ Catalog Consistency
- [x] Both use `catalog_id: general_use`
- [x] Both have empty catalog-level `policy_bindings: []`
- [x] Same grants structure

---

## Expected Behavior After Fix

### Notebook 01 Output (Load Manifest)
```
✓ Loaded ABAC Governance Manifest:
  Bronze flows: 1
  Silver flows: 1
  Total catalogs: 2 (1 bronze + 1 silver, deduplicated to 1)
  Total schemas: 3 (hr, finance, employee_silver)
  Total tables: 5 (1 hr.employees, 3 finance, 1 employee_silver.employees)

✓ Policy inheritance resolved:
  TWO-TIER SCOPING MODEL:
    Schemas with policies (ON SCHEMA): 0
      ↑ All schemas have empty policy_bindings
    
    Schemas delegating to tables (empty policy_bindings): 3
      ↑ hr, finance, employee_silver all check tables
    
    Tables with inherited policies: 0
      ↑ No catalog/schema policies to inherit
    
    Tables with direct policies (ON TABLE): 5
      ↑ All 5 tables have their own policies
```

### Notebook 04 Output (Create Policies)
```
Total policy bindings: 5

CATALOG: 0 bindings
  (No catalog-level policies)

SCHEMA: 0 bindings
  (All schemas have empty policy_bindings)

TABLE: 5 bindings
  general_use.hr.employees <- mnpi_row_filtering
  general_use.finance.accounts_payable <- mnpi_column_masking
  general_use.finance.cash_flow <- mnpi_column_masking
  general_use.finance.accounts_receivable <- mnpi_row_filtering
  general_use.employee_silver.employees <- mnpi_column_masking
```

---

## Schema Naming Note

Bronze and silver use **different schema names**:
- Bronze: `hr`, `finance`
- Silver: `employee_silver`

This is **intentional** because:
1. Different layers (bronze vs silver)
2. Different data transformations
3. Different governance requirements
4. Allows independent evolution

If bronze `hr.employees` feeds silver `employee_silver.employees`, that's handled by SDP-META pipeline orchestration, not governance config.

---

## Validation Commands

Run these in Databricks to verify alignment:

```python
# Notebook 01 - Load and verify structure
manifest = loader.load()

print(f"Catalogs loaded: {len(manifest.catalogs)}")
for cat in manifest.catalogs:
    print(f"  - {cat['catalog_id']}: {cat['policy_bindings']}")

print(f"\nSchemas loaded: {len(manifest.schemas)}")
for sch in manifest.schemas:
    print(f"  - {sch['catalog']}.{sch['schema_id']}: {sch['policy_bindings']}")

print(f"\nTables loaded: {len(manifest.tables)}")
for tbl in manifest.tables:
    print(f"  - {tbl.catalog}.{tbl.schema}.{tbl.table_id}: {tbl.policy_bindings}")
```

Expected output:
```
Catalogs loaded: 1
  - general_use: []

Schemas loaded: 3
  - general_use.hr: []
  - general_use.finance: []
  - general_use.employee_silver: []

Tables loaded: 5
  - general_use.hr.employees: [mnpi_row_filtering]
  - general_use.finance.accounts_payable: [mnpi_column_masking]
  - general_use.finance.cash_flow: [mnpi_column_masking]
  - general_use.finance.accounts_receivable: [mnpi_row_filtering]
  - general_use.employee_silver.employees: [mnpi_column_masking]
```

---

## Summary

✅ **Both files are now fully aligned:**
- Same structure (catalogs → schemas → tables)
- Same catalog definition
- Both follow two-tier scoping correctly
- No orphaned policies (all schemas with policies have tables)
- All policy references are valid
- Consistent with inheritance model

✅ **Ready for deployment:**
```bash
databricks bundle deploy --profile fevm-machine
```

Then run notebooks 01-06 to apply governance!
