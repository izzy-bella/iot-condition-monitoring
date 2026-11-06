# Raspberry Pi live monitoring application

`main.py` is a continuous real-sensor monitoring loop. It does not use the old
environment-value development reader. Each cycle acquires DS18B20, INA226 and
ADXL345 data, processes a vibration window, evaluates condition and maintenance
logic, records event transitions, then publishes one immutable completed reading
to Azure IoT Hub and InfluxDB independently.

## Module layout

- `sensors/` — DS18B20 1-Wire, INA226 SMBus, ADXL345 SPI window acquisition and
  partial-failure coordination
- `processing/vibration.py` — resultant acceleration, detrending, RMS, peak,
  crest factor, kurtosis, NumPy FFT, shaft frequency, RPM, blade-pass frequency
  and dominant frequency
- `diagnostics/condition_evaluator.py` — configurable metric states and stale logic
- `diagnostics/fault_detector.py` — transparent multi-symptom possible-fault rules
- `diagnostics/fmeca.py` — development FMECA lookup and RPN verification
- `diagnostics/health_score.py` — configurable weighted 0–100 health score
- `diagnostics/pipeline.py` — assembles the complete monitoring telemetry
- `storage/event_history.py` — SQLite STARTED/RESOLVED event lifecycle
- `telemetry/azure_iot.py` — Azure IoT Hub adapter
- `telemetry/influxdb_writer.py` — summary, raw vibration and event writes
- `telemetry/fanout.py` — concurrent failure-isolated destination delivery
- `systemd/*.example` — future service template; not installed or enabled

## Hardware configuration

Review `config/sensors.yaml` before first use:

- the proven DS18B20 path is `/sys/bus/w1/devices/28-00001132b5a2/w1_slave`;
- the proven INA226 path is I2C bus 1, address `0x41`, with a `0.005 Ω` shunt;
- the ADXL345 uses SPI bus 0/device 0, mode 3, 2 MHz, full-resolution ±16 g and
  a 3200 Hz output-data-rate configuration;
- confirm SPI, I2C and 1-Wire are enabled on the Raspberry Pi.

The INA226 calculation intentionally preserves the working script: bus voltage
comes from register `0x02`, current is derived from shunt-voltage register
`0x01` and the configured physical shunt, and power is `voltage × current`.

## Vibration window

The initial window is approximately one second and requests 3280 samples, as in
the supplied working script. Acquisition is unpaced and the actual rate is
measured from elapsed monotonic time for FFT frequency bins. Raw timestamps are
derived across that measured window without slowing every SPI transaction.
Static gravity/orientation is removed by subtracting mean resultant magnitude.

The original RMS, Hann FFT, 80–120 Hz shaft search and seven-blade blade-pass
validation are retained. Peak, crest factor, kurtosis, representative XYZ,
dominant frequency and amplitude are added from the same real window.

Vibration thresholds are `null` until baseline testing. The dashboard shows
`THRESHOLDS UNCONFIGURED`; the application does not label arbitrary vibration as
healthy.

## Configuration and secrets

At process startup, `main.py` calls `configuration.load_runtime_environment()`.
That function loads `/home/isabella/.env` with `python-dotenv` and does not
override values already exported by a future systemd service or operator. The
safe variable names and placeholders remain in `.env.example`; the populated
file is outside this repository and must never be committed.

InfluxDB uses `INFLUXDB_URL`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET` and
`INFLUXDB_TOKEN`. Summary telemetry is written to the `fan_condition`
measurement by default, tagged by `deviceId`, at the real observation timestamp.
The complete available summary payload is written as fields; unavailable sensor
values remain absent. Raw acceleration windows and fault lifecycle transitions
remain in their dedicated measurements.

Both outputs default to enabled. Invalid setup for one adapter is logged without
preventing the other from starting. During a cycle, the same immutable reading
is submitted to dedicated Azure and InfluxDB workers. A failure or timeout is
logged per destination and does not escape the fan-out or stop the monitoring
loop.

`BASELINE_ACQUISITION_MODE=true` labels a deliberate baseline run and changes a
normal recommendation to continue collecting real baseline data. It does not
force a score of 100 or bypass configured temperature/current safety rules.

Use a write-only `INFLUXDB_TOKEN` on the Pi. Grafana Cloud should receive a
separate read-only token; see `../grafana/GRAFANA_CLOUD.md`.

## Operation

The production mode is continuous:

```bash
python3 main.py
```

`--once` exists only for commissioning and diagnostics. The loop maintains the
configured cycle period by subtracting acquisition/processing time before its
wait. SIGINT and SIGTERM produce a graceful shutdown.

The future service file is
`systemd/fan-condition-monitoring.service.example`; it is intentionally not
installed or enabled.

## Tests

The current tests cover the proven SPI and INA226 calculations, payload schema,
destination isolation, FFT/shaft/RPM/BPF extraction, threshold boundaries,
stale status and event de-duplication. Install the declared runtime dependencies
before running them on a clean machine:

```bash
python3 -m unittest discover -s tests -v
```
