# InfluxDB schema

The Python writer uses synchronous writes so a per-destination failure is known
to the fan-out layer. InfluxDB point timestamps use the sensor observation time.

## `fan_condition`

One point per completed monitoring cycle.

- tag: `deviceId`
- raw/latest fields when available: `temperature_C`, `voltage_V`, `current_A`,
  `power_W`, `accel_x_g`, `accel_y_g`, `accel_z_g`
- derived fields: `resultant_acceleration_g`, `vibration_rms_g`,
  `vibration_peak_g`, `crest_factor`, `kurtosis`, `dominant_frequency_Hz`,
  `dominant_frequency_amplitude_g`, `shaft_frequency_Hz`, `rpm`,
  `blade_pass_frequency_Hz`, `vibration_sample_rate_Hz`
- diagnostics: `condition_status`, `condition_code`, `suspected_fault`,
  `diagnostic_evidence`, `diagnostic_confidence`, `health_score`
- FMECA/action: `fmeca_rpn`, `fmeca_severity`, `fmeca_occurrence`,
  `fmeca_detectability`, `maintenance_priority`, `recommended_action`
- per-metric status codes used by alerting. Codes are `-2` missing, `-1`
  unconfigured, `0` normal, `1` warning and `2` critical.

Unavailable values are omitted, never filled with zero.

## `fan_vibration_raw`

One point per real ADXL sample, sharing the original sample timestamp.

- tag: `deviceId`
- fields: `accel_x_g`, `accel_y_g`, `accel_z_g`

This measurement supports high-resolution XYZ inspection without inflating the
summary measurement.

## `fan_condition_events`

Written only for STARTED and RESOLVED transitions.

- tags: `deviceId`, `event_id`, `event_state`
- fields: condition, suspected fault, diagnostic evidence, severity, FMECA RPN,
  maintenance priority, recommended action, start and resolution timestamps

The dashboards query `fan_condition` for latest values/trends,
`fan_vibration_raw` for directional vibration and `fan_condition_events` for
history.

## Cloud access

The same writer supports a cloud-accessible InfluxDB HTTPS URL. The Raspberry Pi
should use a write-only token, while Grafana Cloud should use a separate
read-only token. Grafana Cloud cannot reach `localhost` on the Pi. The dashboard
JSON uses SQL/FlightSQL against the InfluxDB Cloud Serverless database.
