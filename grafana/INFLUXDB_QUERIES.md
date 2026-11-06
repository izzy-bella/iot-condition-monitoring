# Live SQL query notes

The dashboard JSON contains live SQL/FlightSQL queries. This file records the
query conventions for future panel changes.

## Latest value

```sql
SELECT time, "temperature_C"
FROM "fan_condition"
WHERE "deviceId" = '${device_id}'
  AND time >= now() - INTERVAL '30 minutes'
  AND "temperature_C" IS NOT NULL
ORDER BY time DESC
LIMIT 1
```

## Trend

```sql
SELECT time, "vibration_rms_g"
FROM "fan_condition"
WHERE "deviceId" = '${device_id}'
  AND $__timeFilter(time)
  AND "vibration_rms_g" IS NOT NULL
ORDER BY time
```

The detailed dashboard uses the same latest-value pattern for
`shaft_frequency_Hz`, `rpm`, `blade_pass_frequency_Hz` and
`dominant_frequency_Hz`. These are calculated from the same real acceleration
window rather than independent or simulated values.

## Stale-data pattern

Status and action panels union the last real record with an epoch fallback, sort
by timestamp and compare the result with the 30-second timeout. This
works even when the bucket contains no record for the device. Alert queries use
the same logic but return numeric `1` for stale and `0` for fresh.

Grafana-managed alert queries cannot use dashboard template variables, so the
provisioned alert YAML uses Grafana environment substitution for
`INFLUXDB_BUCKET` and `DEVICE_ID`.

For Grafana Cloud, classic on-disk alert provisioning is unavailable. Import
equivalent rules through the Alerting provisioning HTTP API, Terraform, or the
Cloud UI, as described in `GRAFANA_CLOUD.md`.

## Event history

```sql
SELECT time, "event_id", "event_state", "condition", "suspected_fault",
       "diagnostic_evidence", "severity", "fmeca_rpn",
       "maintenance_priority", "recommended_action", "started_at", "resolved_at"
FROM "fan_condition_events"
WHERE "deviceId" = '${device_id}'
  AND time >= now() - INTERVAL '30 days'
ORDER BY time DESC
LIMIT 100
```
