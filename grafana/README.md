# Grafana live monitoring

Grafana is provisioned against datasource UID `iiot-influxdb`. The dashboard
JSON contains live SQL/FlightSQL queries; it no longer generates demonstration
waveforms or production-looking fabricated values.

## Provisioned artifacts

- `dashboards/fan-condition-monitoring.json` — prototype-matched landing screen
- `dashboards/fan-condition-diagnostics.json` — vibration, diagnosis, FMECA and
  fault-history detail
- `provisioning/dashboards/fan-condition-monitoring.yaml` — file provider
- `provisioning/datasources/influxdb.yaml` — live SQL datasource using environment
  variables
- `provisioning/datasources/preview.yaml` — retained bundled datasource from the
  earlier project layer, but unused by the live dashboards
- `provisioning/alerting/rules.yaml` — warning, critical, diagnostic and stale rules

No contact point, email address, Teams webhook or credential is configured.

## Environment

Grafana needs `INFLUXDB_URL`, `INFLUXDB_BUCKET`,
`INFLUXDB_GRAFANA_READ_TOKEN`, `DEVICE_ID` and `STALE_TIMEOUT_SECONDS` in its own
process environment. The SQL datasource uses `INFLUXDB_BUCKET` as its database.
Keep `STALE_TIMEOUT_SECONDS`, the hidden dashboard `stale_timeout_seconds`
constant, and `config/thresholds.yaml` aligned when changing the initial
30-second timeout.

Mount or copy:

| Repository path | Grafana path |
|---|---|
| `grafana/provisioning` | `/etc/grafana/provisioning` |
| `grafana/dashboards` | `/var/lib/grafana/dashboards/fan-condition-monitoring` |

Nothing in this repository starts Grafana or Docker.

For the final hosted deployment, follow [GRAFANA_CLOUD.md](GRAFANA_CLOUD.md).
Grafana Cloud must be able to reach the InfluxDB endpoint directly or through
Private Data Source Connect. The dashboards target the configured InfluxDB
Cloud Serverless SQL datasource.

## Live landing screen

The first dashboard retains the supplied prototype hierarchy: identity header,
full-width status, four gauges, three trends, alert/history, health score,
recommended action, device information and threshold key. It opens at 15 minutes
and refreshes every 5 seconds.

System status queries independently enforce a 30-second freshness check. When
the latest point is too old, the banner becomes `OFFLINE / NO DATA`, the action
explains what to check, and the health query returns no value.

## Detailed screen

The linked detail dashboard includes:

- Vibration RMS and peak;
- **Vibration by Direction (XYZ)** for raw `accel_x_g`, `accel_y_g`, `accel_z_g`;
- **Vibration Spike Level** for internal `crest_factor`;
- **Vibration Impact Level** for internal `kurtosis`;
- dominant frequency, shaft frequency, estimated RPM, seven-blade blade-pass
  frequency and vibration trends;
- current condition, possible fault and diagnostic evidence;
- **FMECA (Risk Assessment)** with S/O/D values and RPN;
- maintenance priority and transition-based fault history.

## Alert behaviour

Warning and critical rules are multi-dimensional: the triggering status-code
field identifies temperature, current, vibration RMS, vibration peak, spike
level or impact level. Pending periods suppress transient samples. Overall
diagnostic and stale-data rules are separate. Grafana retains firing/resolved
state and sends recovery notifications once a contact point is deliberately
configured later.

The on-disk alerting file is suitable for self-hosted Grafana. Grafana Cloud
requires its Alerting HTTP API, Terraform, or UI because classic file-based
alert provisioning is not available there.

## Native Grafana limitations

- Grafana owns toolbar, time picker, fonts and application navigation, so exact
  dimensions vary by release.
- Core gauge arc thickness and label position are not pixel-configurable.
- Panel radius and chrome follow the selected dark theme.
- Core panels cannot nest the current alert banner and history table inside one
  border, so they remain aligned as two panels.

The design avoids unsigned/custom panels and remains portable across supported
Grafana releases.
