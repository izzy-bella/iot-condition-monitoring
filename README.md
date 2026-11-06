# Live IoT fan condition monitoring

An explainable Industrial IoT condition-monitoring and preventive-maintenance
system for a rotating 12 V DC fan. The repository combines real Raspberry Pi
sensor acquisition, windowed vibration processing, rule-based diagnostics,
development FMECA decision support, Azure IoT Hub publishing, InfluxDB storage,
Grafana dashboards and provisioned alert rules.

The implementation does not generate production telemetry. Missing or failed
sensors remain missing, affect the diagnosis, and are never replaced with made-up
values.

## Live data flow

```text
DS18B20 (1-Wire) + INA226 (I2C) + ADXL345 (SPI)
              │
              ▼
Raspberry Pi continuous acquisition
              │
              ▼
Windowed vibration processing
              │
              ▼
Condition rules → possible-fault diagnosis → FMECA → health score → action
              │
              ▼
One immutable complete telemetry object
              ├──────────────► Azure IoT Hub
              └──────────────► cloud-accessible InfluxDB
                                      │
                                      ▼
                            Grafana Cloud dashboards and alerts
```

Azure IoT Hub and InfluxDB remain independent destinations. Each publish is
executed and logged independently; a failure or timeout in one does not prevent
the other from receiving the same evaluated observation.

## Repository layers

- [`raspberry-pi/`](raspberry-pi/README.md) — hardware acquisition, processing,
  diagnostics, FMECA, health scoring, event lifecycle and independent publishing
- [`config/`](config/thresholds.yaml) — development thresholds, hardware settings
  and configurable FMECA entries
- [`influxdb/`](influxdb/README.md) — measurement and query schema
- [`grafana/`](grafana/README.md) — live landing dashboard, detailed vibration and
  diagnostics dashboard, datasource/dashboard/alert provisioning
- [`grafana/GRAFANA_CLOUD.md`](grafana/GRAFANA_CLOUD.md) — final hosted data-source,
  dashboard import, alerting and Viewer-role hand-off
- [`docs/architecture.md`](docs/architecture.md) — complete architecture and
  rationale suitable for the MSc project report

## Important development status

- Temperature and current values in `config/thresholds.yaml` are development
  thresholds, not experimentally validated limits.
- Vibration, voltage, power and frequency limits are deliberately `null` until
  baseline tests justify them. The code reports them as unconfigured rather than
  pretending a safe range is known.
- FMECA severity, occurrence and detectability values are configurable development
  assessments and must be reviewed against project evidence.
- The sensor configuration now preserves the supplied working hardware paths:
  ADXL345 over SPI, INA226 address `0x41` with a `0.005 Ω` shunt, and the explicit
  DS18B20 device path.
- No container, SDK, systemd unit or service is installed, started or enabled by
  this repository.

## Security

No credentials are committed. Azure and InfluxDB credentials are read from the
runtime environment. Copy only the variable names from
[`raspberry-pi/.env.example`](raspberry-pi/.env.example) into the Raspberry Pi's
protected process-manager configuration. `.env`, SQLite runtime databases,
Python caches and virtual environments are ignored by Git.
