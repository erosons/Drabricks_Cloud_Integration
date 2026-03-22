-- ─────────────────────────────────────────────
-- notebooks/validate_abac_policies.sql
--
-- Run this notebook in your Databricks workspace
-- to validate that row filters and column masks
-- are behaving correctly after deployment.
--
-- Sections:
--   1. Introspect attached policies per table
--   2. Verify filter function definitions
--   3. Test row filter output per group (impersonation)
--   4. Test column mask output per group
--   5. Audit grant inventory
-- ─────────────────────────────────────────────


-- ══════════════════════════════════════════════
-- 1. List all tables with attached row filters
-- ══════════════════════════════════════════════

SELECT
    table_catalog,
    table_schema,
    table_name,
    row_filter_function_name
FROM information_schema.tables
WHERE table_catalog LIKE '%_finance'    -- adjust to your catalog pattern
  AND row_filter_function_name IS NOT NULL
ORDER BY table_catalog, table_schema, table_name;


-- ══════════════════════════════════════════════
-- 2. List all columns with attached masks
-- ══════════════════════════════════════════════

SELECT
    table_catalog,
    table_schema,
    table_name,
    column_name,
    mask_function_name
FROM information_schema.columns
WHERE table_catalog LIKE '%_finance'
  AND mask_function_name IS NOT NULL
ORDER BY table_catalog, table_schema, table_name, column_name;


-- ══════════════════════════════════════════════
-- 3. Inspect filter function body
-- ══════════════════════════════════════════════

SELECT
    routine_catalog,
    routine_schema,
    routine_name,
    routine_definition,
    routine_type,
    created,
    last_altered
FROM information_schema.routines
WHERE routine_schema = '_policies'
  AND routine_catalog LIKE '%_finance'
ORDER BY routine_name;


-- ══════════════════════════════════════════════
-- 4. Count rows visible per region
-- (run as a user in each group to validate)
-- Replace prd_finance.core.ledger with your table
-- ══════════════════════════════════════════════

-- As a user in prd_finance_ledger_region_apac → should only see APAC rows
SELECT region, COUNT(*) AS row_count
FROM prd_finance.core.ledger
GROUP BY region
ORDER BY region;
-- Expected: only region = 'APAC' visible

-- As a user in prd_finance_ledger_region_global → should see all regions
-- (run as that user or use EXECUTE AS if you have the privilege)


-- ══════════════════════════════════════════════
-- 5. Verify PII masking
-- ══════════════════════════════════════════════

-- As a user in prd_finance_ledger_pii_masked:
-- customer_name should be a 64-char hex string (SHA-256)
SELECT
    id,
    customer_name,
    LENGTH(customer_name) AS name_length,
    CASE
        WHEN customer_name RLIKE '^[0-9a-f]{64}$' THEN 'MASKED_OK'
        WHEN customer_name IS NULL                  THEN 'NULL_DENIED'
        ELSE                                             'CLEAR_TEXT'
    END AS pii_status
FROM prd_finance.core.ledger
LIMIT 20;


-- ══════════════════════════════════════════════
-- 6. Verify financial masking
-- ══════════════════════════════════════════════

-- As a user in prd_finance_ledger_financial_masked:
-- amount should be rounded to nearest 1000
SELECT
    id,
    amount,
    amount % 1000 AS remainder,   -- should be 0 if masked
    CASE
        WHEN amount IS NULL     THEN 'NULL_DENIED'
        WHEN amount % 1000 = 0  THEN 'MASKED_OK'
        ELSE                         'CLEAR_VALUE'
    END AS financial_status
FROM prd_finance.core.ledger
LIMIT 20;


-- ══════════════════════════════════════════════
-- 7. Full grant inventory — who has SELECT
--    on which tables in a catalog
-- ══════════════════════════════════════════════

SELECT
    grantee,
    privilege_type,
    table_catalog,
    table_schema,
    table_name,
    is_grantable
FROM information_schema.table_privileges
WHERE table_catalog LIKE '%_finance'
  AND privilege_type = 'SELECT'
ORDER BY table_catalog, table_schema, table_name, grantee;


-- ══════════════════════════════════════════════
-- 8. Detect tables WITHOUT a row filter
--    (potential ungated tables in policy domains)
-- ══════════════════════════════════════════════

SELECT
    table_catalog,
    table_schema,
    table_name,
    'NO_ROW_FILTER' AS warning
FROM information_schema.tables
WHERE table_catalog LIKE 'prd_%'    -- production catalogs only
  AND table_schema != '_policies'   -- exclude policy function schema
  AND table_type = 'MANAGED'
  AND row_filter_function_name IS NULL
ORDER BY table_catalog, table_schema, table_name;


-- ══════════════════════════════════════════════
-- 9. Detect PII-tagged columns WITHOUT a mask
--    (requires column tags to be set)
-- ══════════════════════════════════════════════

SELECT
    c.table_catalog,
    c.table_schema,
    c.table_name,
    c.column_name,
    ct.tag_value  AS pii_tag,
    'UNMASKED_PII' AS warning
FROM information_schema.columns c
JOIN information_schema.column_tags ct
  ON  ct.table_catalog = c.table_catalog
  AND ct.table_schema  = c.table_schema
  AND ct.table_name    = c.table_name
  AND ct.column_name   = c.column_name
  AND ct.tag_name      = 'pii'
  AND ct.tag_value     = 'true'
WHERE c.mask_function_name IS NULL
  AND c.table_catalog LIKE 'prd_%'
ORDER BY c.table_catalog, c.table_name, c.column_name;
