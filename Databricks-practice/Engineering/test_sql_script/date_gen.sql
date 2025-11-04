WITH date_series AS (
  SELECT
    explode(sequence(to_date('2014-01-01'), to_date('2050-12-31'), interval 1 day)) AS d
)
SELECT
  *
FROM
  date_series
limit 10