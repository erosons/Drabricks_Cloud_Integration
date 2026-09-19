

%sql
    CREATE OR REPLACE FUNCTION city_bike.default.dynamic_making(x STRING)
    RETURNs STRING
    RETURN CONCAT(REPEAT("*",LENGTH(x)-4),RIGHT(x,4))