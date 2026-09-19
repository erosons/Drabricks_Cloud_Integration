
### SQL UDFs and Control Flow

-- ### Learning Objectives
-- # By the end of this lesson, you should be able to:
-- # * Define and registering SQL UDFs
-- # * Describe the security model used for sharing SQL UDFs
-- # * Use **`CASE`** / **`WHEN`** statements in SQL code
-- # * Leverage **`CASE`** / **`WHEN`** statements in SQL UDFs for custom control flow


CREATE OR REPLACE FUNCTION item_preference(name STRING, price INT)
RETURNS STRING
RETURN CASE 
  WHEN name = "Standard Queen Mattress" THEN "This is my default mattress"
  WHEN name = "Premium Queen Mattress" THEN "This is my favorite mattress"
  WHEN price > 100 THEN concat("I'd wait until the ", name, " is on sale for $", round(price * 0.8, 0))
  ELSE concat("I don't need a ", name)
END;

SELECT *, item_preference(name, price) FROM item_lookup