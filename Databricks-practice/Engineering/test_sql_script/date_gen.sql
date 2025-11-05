CREATE TABLE IF NOT EXISTS mysandbox.silver.dim_date
AS
WITH date_series AS (
  SELECT
    explode(
      sequence(
        to_date('2014-01-01'),
        to_date('2050-12-31'),
        interval 1 day
      )
    ) AS d
)
SELECT
  d AS date,
  year(d) AS year,
  month(d) AS month,
  day(d) AS day,
  0 AS hour,
  0 AS minute
FROM
  date_series