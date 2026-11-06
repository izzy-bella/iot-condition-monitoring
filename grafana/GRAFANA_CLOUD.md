# Grafana Cloud deployment hand-off

Grafana Cloud is the intended authorised-user landing point. This repository
does not deploy it automatically and contains no Cloud access token, InfluxDB
token, user invitation, or notification endpoint.

## Data path

The Raspberry Pi writes directly to a cloud-accessible InfluxDB endpoint using
the existing `InfluxDBWriter`. Grafana Cloud queries that InfluxDB endpoint; it
does not receive the telemetry from Azure IoT Hub and it cannot query a Pi-only
`localhost:8086` address over the public internet.

The version-controlled dashboards use SQL/FlightSQL for the InfluxDB Cloud
Serverless datasource configured for this project.

## Credential separation

Create two independent least-privilege credentials:

1. a write-only token for the Raspberry Pi, supplied as `INFLUXDB_TOKEN` in the
   protected Pi process environment;
2. a read-only token for Grafana Cloud, entered into Grafana's secure Token
   field.

Do not reuse the Azure device key for either purpose. Do not commit either token.

## Connect Grafana Cloud

An authorised Grafana Cloud Administrator should:

1. open **Connections → Data sources → Add new data source → InfluxDB**;
2. enter the externally reachable HTTPS InfluxDB URL;
3. select **InfluxDB Cloud Serverless** and **SQL** query language;
4. enter the database/bucket name and read-only token;
5. select **Save & test**;
6. ensure the data-source UID used by the dashboards is `iiot-influxdb`, or
   replace that UID in both dashboard JSON files during import;
7. import `dashboards/fan-condition-monitoring.json` and
   `dashboards/fan-condition-diagnostics.json`;
8. confirm the `device_id` variable matches the Raspberry Pi telemetry tag.

Direct network access or Grafana Private Data Source Connect is required when
InfluxDB is private. A public endpoint must use TLS and appropriate network
access controls.

## Alerts

`provisioning/alerting/rules.yaml` remains the version-controlled self-hosted
Grafana rule definition. Grafana Cloud does not consume classic on-disk alert
provisioning files. During Cloud deployment, create/import the equivalent rules
using the Grafana Alerting provisioning HTTP API, Terraform, or the Cloud UI,
then test warning, critical, stale, and recovery states. Add a real contact point
only after the intended recipient approves it.

## Supervisor access

Invite the supervisor to the Grafana Cloud organization and assign **Viewer**.
Grant Viewer access to the `IIoT Monitoring` folder. Viewer access prevents
dashboard editing while allowing the live panels, time-range changes, vibration
detail, diagnostic evidence, FMECA values, actions, and history to be viewed.

## Acceptance checks

- Latest telemetry time advances while the fan monitor is running.
- Both dashboards refresh at five seconds and open at the last 15 minutes.
- Disconnecting telemetry changes the status to OFFLINE after the configured
  timeout and removes the health value.
- A controlled warning produces one pending/firing alert and a resolved state.
- Viewer accounts can see all panels but cannot save dashboard edits.
- No write-capable InfluxDB or Azure credential is exposed to a Viewer.

Official references:

- <https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/influxdb/configure/>
- <https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/alerting/set-up/provision-alerting-resources/>
- <https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/cloud-roles/>
