"""v232: an append-only JSONL checkpoint, one fsynced line per finished unit.

working-conventions.md, Long runs must checkpoint: a restart reads done() and skips
those units. A torn last line (the run was killed mid-write) is dropped on open.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class JsonlCheckpoint:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._repair()

    def _repair(self) -> None:
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        if data and not data.endswith(b"\n"):
            with open(self.path, "r+b") as fh:
                fh.truncate(data.rfind(b"\n") + 1)

    def _entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{self.path}: line {number} is not JSON") from exc
            entries.append(entry)
        return entries

    def done(self) -> set[str]:
        return {entry["key"] for entry in self._entries()}

    def append(self, key: str, row: dict) -> None:
        line = json.dumps({"key": key, "row": row}, sort_keys=True, allow_nan=False) + "\n"
        with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def rows(self) -> list[dict]:
        latest: dict[str, dict] = {}
        for entry in self._entries():
            latest[entry["key"]] = entry["row"]
        return list(latest.values())
