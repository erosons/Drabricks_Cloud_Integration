SELECT
  timestamp,
  message
FROM event_log(TABLE(main.default.gold_sales))
WHERE event_type = 'planning_information'
ORDER BY timestamp DESC;
