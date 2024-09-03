### Translate endpoint usage per oganisation

```sql
SELECT 
    COALESCE(organization, 'Others') AS organization,
    COUNT(*) AS translate_usage_count
FROM 
    endpoint_logs
WHERE 
    date IS NOT NULL 
    AND endpoint = '/tasks/nllb_translate'
    AND date >= NOW() - INTERVAL '30 minutes'
GROUP BY 
    COALESCE(organization, 'Others');
```

```sql
SELECT 
    COALESCE(organization, 'Others') AS organization,
    COUNT(*) AS translate_usage_count
FROM 
    endpoint_logs
WHERE 
    date IS NOT NULL 
    AND endpoint = '/tasks/nllb_translate'
GROUP BY 
    COALESCE(organization, 'Others');
```

#### Graphana

```sql
SELECT 
    COALESCE(organization, 'Others') AS organization,
    COUNT(*) AS translate_usage_count
FROM 
    endpoint_logs
WHERE 
    date IS NOT NULL
    AND date BETWEEN $__timeFrom() AND $__timeTo()
    AND endpoint = '/tasks/nllb_translate'
GROUP BY 
    COALESCE(organization, 'Others');
```

### Speech endpoint usage per oganisation

```sql
SELECT 
    COALESCE(organization, 'Others') AS organization,
    COUNT(*) AS translate_usage_count
FROM 
    endpoint_logs
WHERE 
    date IS NOT NULL 
    AND endpoint = '/tasks/stt'
GROUP BY 
    COALESCE(organization, 'Others');
```

#### Graphana

```sql
SELECT 
    COALESCE(organization, 'Others') AS organization,
    COUNT(*) AS speech_usage_count
FROM 
    endpoint_logs
WHERE 
    date IS NOT NULL
    AND date BETWEEN $__timeFrom() AND $__timeTo()
    AND endpoint = '/tasks/stt'
GROUP BY 
    COALESCE(organization, 'Others');
```

```sql
SELECT 
    COALESCE(endpoint) AS endpoints,
    COUNT(*) AS endpoint_usage_count
FROM 
    endpoint_logs
WHERE 
    date BETWEEN $__timeFrom() AND $__timeTo()
GROUP BY 
    COALESCE(endpoint);
```

### User endpoint usage

```sql
SELECT 
    username as user,
    COUNT(*) AS user_usage_count
FROM 
    endpoint_logs
WHERE 
    date IS NOT NULL
    AND date BETWEEN $__timeFrom() AND $__timeTo()
    AND endpoint = '/tasks/nllb_translate'
GROUP BY 
    username;
```
