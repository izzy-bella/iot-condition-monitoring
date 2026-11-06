"""SQLite-backed fault lifecycle tracking without per-cycle event duplication."""

from datetime import timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from telemetry.models import TelemetryReading


class FaultEventTracker:
    def __init__(self, database_path: str) -> None:
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fault_events (
                event_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                resolved_at TEXT,
                condition TEXT NOT NULL,
                suspected_fault TEXT NOT NULL,
                diagnostic_evidence TEXT NOT NULL,
                severity INTEGER NOT NULL,
                fmeca_rpn INTEGER NOT NULL,
                maintenance_priority TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                active INTEGER NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_fault_events_active ON fault_events(device_id, active)"
        )
        self._connection.commit()

    def _active(self, device_id: str) -> Optional[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM fault_events WHERE device_id = ? AND active = 1 ORDER BY started_at DESC LIMIT 1",
            (device_id,),
        ).fetchone()

    @staticmethod
    def _transition(row: Dict[str, Any], event_state: str) -> Dict[str, Any]:
        transition = dict(row)
        transition["event_state"] = event_state
        return transition

    def update(self, reading: TelemetryReading) -> Tuple[Dict[str, Any], ...]:
        """Create transitions only for begin, material change, or recovery."""

        timestamp = reading.observed_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        active = self._active(reading.device_id)
        is_fault = reading.condition_status in {"WARNING", "CRITICAL", "OFFLINE"}
        new_key = (
            reading.condition_status or "UNKNOWN",
            reading.suspected_fault or "Unspecified condition",
            reading.maintenance_priority or "UNSPECIFIED",
        )
        transitions: List[Dict[str, Any]] = []

        if active is not None:
            active_key = (
                active["condition"],
                active["suspected_fault"],
                active["maintenance_priority"],
            )
            if not is_fault or active_key != new_key:
                self._connection.execute(
                    "UPDATE fault_events SET active = 0, resolved_at = ? WHERE event_id = ?",
                    (timestamp, active["event_id"]),
                )
                resolved = dict(active)
                resolved["active"] = 0
                resolved["resolved_at"] = timestamp
                transitions.append(self._transition(resolved, "RESOLVED"))
                active = None

        if is_fault and active is None:
            event = {
                "event_id": str(uuid4()),
                "device_id": reading.device_id,
                "started_at": timestamp,
                "resolved_at": None,
                "condition": reading.condition_status or "UNKNOWN",
                "suspected_fault": reading.suspected_fault or "Unspecified condition",
                "diagnostic_evidence": reading.diagnostic_evidence or "No evidence supplied",
                "severity": int(reading.fmeca_severity or 0),
                "fmeca_rpn": int(reading.fmeca_rpn or 0),
                "maintenance_priority": reading.maintenance_priority or "UNSPECIFIED",
                "recommended_action": reading.recommended_action or "Investigate condition",
                "active": 1,
            }
            self._connection.execute(
                """
                INSERT INTO fault_events (
                    event_id, device_id, started_at, resolved_at, condition,
                    suspected_fault, diagnostic_evidence, severity, fmeca_rpn,
                    maintenance_priority, recommended_action, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(event[column] for column in (
                    "event_id", "device_id", "started_at", "resolved_at", "condition",
                    "suspected_fault", "diagnostic_evidence", "severity", "fmeca_rpn",
                    "maintenance_priority", "recommended_action", "active"
                )),
            )
            transitions.append(self._transition(event, "STARTED"))

        self._connection.commit()
        return tuple(transitions)

    def close(self) -> None:
        self._connection.close()
