"""Durable append-only, hash-chained decision/assignment/outcome ledger."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AppendOnlyPilotLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def records(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        return tuple(json.loads(line) for line in self.path.read_text().splitlines() if line)

    def append(
        self,
        *,
        record_id: str,
        record_type: str,
        payload: dict[str, Any],
        recorded_at: datetime | None = None,
    ) -> str:
        existing = self.records()
        if any(row["record_id"] == record_id for row in existing):
            raise ValueError("pilot ledger record IDs are immutable and unique")
        previous_hash = existing[-1]["record_hash"] if existing else "GENESIS"
        timestamp = recorded_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("ledger timestamp must be timezone-aware")
        record = {
            "record_id": record_id,
            "record_type": record_type,
            "recorded_at": timestamp.isoformat(),
            "previous_hash": previous_hash,
            "payload": payload,
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        record["record_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        return str(record["record_hash"])

    def verify(self) -> bool:
        previous_hash = "GENESIS"
        seen: set[str] = set()
        for row in self.records():
            if row["record_id"] in seen or row["previous_hash"] != previous_hash:
                return False
            stored_hash = row["record_hash"]
            content = {key: value for key, value in row.items() if key != "record_hash"}
            canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(canonical.encode()).hexdigest() != stored_hash:
                return False
            seen.add(row["record_id"])
            previous_hash = stored_hash
        return True
