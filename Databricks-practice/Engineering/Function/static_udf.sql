

# SQL Version
1.  CREATE OR REPLACE FUNCTION sale_announcement(item_name STRING, item_price INT)
    RETURNS STRING
    RETURN concat("The ", item_name, " is on sale for $", round(item_price * 0.8, 0));

    # SELECT *, sale_announcement(name, price) AS message FROM item_lookup

2.  CREATE OR REPLACE FUNCTION sale__discount_announcement(item_name STRING,item_pice INT,discounted_price FLOAT)
    RETURNS STRING
    RETURN concat("The ",item_name, " is on sale for discounted proce $", round(item_pice * discounted_price, 1), " discounted_price:" , discounted_price)

    # SELECT *, sale__discount_announcement(name, price, 0.8) AS message FROM item_lookup