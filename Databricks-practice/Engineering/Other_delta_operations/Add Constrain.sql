-- Add a Table Constraint
-- Databricks supports adding constraints to Delta tables to enforce data quality and integrity. Constraints are rules that data must follow in order to be added to a table. If a constraint is violated, the write operation will fail.
-- Because Delta Lake enforces schema on write, Databricks can support standard SQL constraint management clauses to ensure the quality and integrity of data added to a table.

-- Databricks currently support two types of constraints:

--     NOT NULL constraints
--     CHECK constraints

-- In both cases, you must ensure that no data violating the constraint is already in the table prior to defining the constraint. Once a constraint has been added to a table, data violating the constraint will result in write failure.

-- Below, we'll add a CHECK constraint to the date column of our table. Note that CHECK constraints look like standard WHERE clauses you might use to filter a dataset.


ALTER TABLE purchase_dates ADD CONSTRAINT valid_date CHECK (Shipdate >= '2020-01-01');