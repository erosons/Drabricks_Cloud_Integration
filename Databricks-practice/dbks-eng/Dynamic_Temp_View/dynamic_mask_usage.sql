%sql
CREATE OR REPLACE VIEW city_bike.default.vwsilver
AS 
SELECT *, city_bike.default.dynamic_making(name) as name2
FROM city_bike.default.silver