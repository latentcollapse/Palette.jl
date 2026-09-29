SELECT queue, id FROM (
  SELECT queue, id, priority,
         ROW_NUMBER() OVER (PARTITION BY queue ORDER BY priority DESC, id) AS n
  FROM jobs WHERE status = 'queued'
) WHERE n <= 2 ORDER BY queue, priority DESC, id;
