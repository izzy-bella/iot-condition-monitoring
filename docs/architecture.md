# System architecture and decision flow

## Purpose

The system monitors a 12 V DC fan continuously while it is running. It combines
thermal, electrical and vibration observations to support condition awareness,
possible-fault diagnosis and preventive-maintenance decisions. The initial
implementation uses transparent rules so every status and recommendation can be
traced to sensor evidence and configuration.

## Acquisition and processing sequence

1. `SensorAcquisition` reads the working DS18B20 1-Wire path, INA226 at I2C
   address `0x41`, and the ADXL345 over SPI bus 0/device 0 independently.
2. A failed sensor produces a named error while successful sensor readings are
   preserved. No numeric substitute is generated.
3. The ADXL345 uses the supplied mode-3, 2 MHz SPI commands, full-resolution
   ±16 g format and 3200 Hz output-data-rate setting. The acquisition loop reads
   an unpaced approximately one-second window of 3280 samples, matching the
   previously measured live script. Actual sample rate is measured per window.
4. `calculate_vibration_features` calculates resultant acceleration, removes its
   mean/gravity component, and derives RMS, absolute peak, crest factor and
   non-excess kurtosis.
5. A NumPy Hann window and real FFT preserve the working spectrum calculation.
   The strongest non-DC bin is reported as dominant frequency. Candidate peaks
   from 80–120 Hz are scored using their corresponding seven-blade blade-pass
   region, producing shaft frequency, RPM and detected blade-pass frequency.
6. `ConditionEvaluator` evaluates every available field against
   `config/thresholds.yaml`. Unset limits produce `UNCONFIGURED`, not `NORMAL`.
7. `FaultDetector` combines symptoms to produce a possible fault, evidence and
   confidence level. It does not claim that an uncertain diagnosis is confirmed.
8. `FMECAEvaluator` selects the matching configurable failure mode and verifies
   `RPN = severity × occurrence × detectability`.
9. `HealthScoreCalculator` forms a documented weighted score from the available
   temperature, electrical, vibration, diagnostic and availability components.
   OFFLINE data produces no health score.
10. `FaultEventTracker` writes lifecycle transitions to SQLite only when a fault
    starts, materially changes or resolves.
11. The same immutable completed telemetry object is published concurrently to
    Azure IoT Hub and a local or cloud-accessible InfluxDB endpoint.

## Continuous timing

`main.py` runs continuously by default. Each cycle includes acquisition and
processing time; it then waits only for the remainder of
`TELEMETRY_INTERVAL_SECONDS`. A one-cycle `--once` option exists for commissioning
checks, but is not the production operating mode. The example systemd unit is not
installed or enabled.

The initial telemetry interval is 10 seconds, matching the supplied live
script's approximate send interval. The one-second vibration window is part of
each cycle; the loop waits only for the remaining cycle time.

## Condition and diagnosis logic

Overall status is the highest active configured severity across temperature,
electrical and vibration metrics, with additional escalation for missing sensor
groups. The state values are `NORMAL`, `WARNING`, `CRITICAL` and `OFFLINE`.

Diagnosis rules use combinations where evidence exists:

- kurtosis plus crest factor/peak → possible bearing degradation;
- crest factor or repeated impact evidence → suspected mechanical looseness;
- vibration RMS plus frequency change or sustained increase → possible imbalance;
- current plus power/vibration → elevated load or mechanical resistance;
- temperature plus electrical load → overload with heating;
- voltage outside configured bounds → power-supply abnormality;
- sensor read/processing errors → sensor fault;
- stale dashboard telemetry → communications/telemetry fault.

Rules relying on an unset threshold remain inactive until the threshold is
configured from baseline evidence.

## Health score

The score is a weighted average configured in `thresholds.yaml`:

| Component | Development weight |
|---|---:|
| Temperature | 25% |
| Electrical | 25% |
| Vibration | 25% |
| Diagnostic condition | 15% |
| Data availability | 10% |

Configured metric states currently map to 100 (normal), 65 (warning) and 20
(critical). Unconfigured components are excluded and therefore visible in the
configuration rather than silently treated as healthy. Sensor errors reduce the
availability component. Stale/offline telemetry returns `None`, so Grafana cannot
show a falsely healthy percentage.

## Stale data

The Raspberry Pi can identify an old supplied snapshot, but cannot report its own
power loss. Therefore Grafana status and alert queries independently compare the
latest InfluxDB timestamp with the configurable initial 30-second timeout. They
produce OFFLINE / NO DATA and the operator message even when the application is
not running. Grafana alert-state history preserves this external outage; local
SQLite cannot write while the Pi is offline.

## Cloud user path

For the final deployment, the Pi writes to a cloud-accessible InfluxDB endpoint
with a write-only token. Grafana Cloud connects using a different read-only
token and queries the same measurements. Azure IoT Hub continues independently
and is not replaced by the dashboard path. A Grafana Cloud Viewer can see live
and historical dashboard content without dashboard-edit permission. Classic
on-disk Grafana alert provisioning is retained for self-hosting; Cloud alert
rules must be imported through its API, Terraform, or UI.

## Alert and event lifecycle

Application fault events are transition-based. One persistent condition produces
one STARTED record and eventually one RESOLVED record. Severity, diagnosis or
maintenance-priority changes close the previous event and start a new one.

Grafana rules use 10–30 second pending periods and multi-dimensional metric
labels. This prevents a five-second dashboard refresh from becoming a five-second
notification stream. Grafana automatically produces resolved state transitions.
No contact point or real recipient is provisioned.
