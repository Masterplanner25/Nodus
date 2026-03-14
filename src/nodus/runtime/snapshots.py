"""Snapshot manager for session state."""

from __future__ import annotations

import pickle
import os
import time
import uuid
from dataclasses import dataclass

from nodus.support.config import SNAPSHOT_DIR, MAX_SNAPSHOTS


@dataclass
class Snapshot:
    snapshot_id: str
    session_id: str
    timestamp: float
    state_blob: dict


class SnapshotManager:
    def __init__(self, *, snapshot_dir: str = SNAPSHOT_DIR, max_snapshots: int = MAX_SNAPSHOTS):
        self.snapshot_dir = snapshot_dir
        self.max_snapshots = max_snapshots
        os.makedirs(self.snapshot_dir, exist_ok=True)

    def _path(self, snapshot_id: str) -> str:
        return os.path.join(self.snapshot_dir, f"{snapshot_id}.pkl")

    def create(self, session_id: str, state_blob: dict) -> Snapshot:
        self.cleanup()
        if self.max_snapshots is not None and len(self.list_snapshots()) >= self.max_snapshots:
            self._evict_oldest()
        snapshot_id = f"snap_{uuid.uuid4().hex[:8]}"
        timestamp = time.time()
        snapshot = Snapshot(snapshot_id=snapshot_id, session_id=session_id, timestamp=timestamp, state_blob=state_blob)
        payload = {
            "snapshot_id": snapshot.snapshot_id,
            "session_id": snapshot.session_id,
            "timestamp": snapshot.timestamp,
            "state_blob": snapshot.state_blob,
        }
        with open(self._path(snapshot_id), "wb") as f:
            pickle.dump(payload, f)
        return snapshot

    def get(self, snapshot_id: str) -> Snapshot | None:
        path = self._path(snapshot_id)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            payload = pickle.load(f)
        return Snapshot(
            snapshot_id=payload["snapshot_id"],
            session_id=payload["session_id"],
            timestamp=payload["timestamp"],
            state_blob=payload["state_blob"],
        )

    def delete(self, snapshot_id: str) -> bool:
        path = self._path(snapshot_id)
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True

    def list_snapshots(self) -> list[dict]:
        entries = []
        if not os.path.isdir(self.snapshot_dir):
            return entries
        for name in os.listdir(self.snapshot_dir):
            if not name.endswith(".pkl"):
                continue
            path = os.path.join(self.snapshot_dir, name)
            try:
                with open(path, "rb") as f:
                    payload = pickle.load(f)
                entries.append(
                    {
                        "snapshot_id": payload.get("snapshot_id"),
                        "session_id": payload.get("session_id"),
                        "timestamp": payload.get("timestamp"),
                    }
                )
            except Exception:
                continue
        entries.sort(key=lambda item: item.get("timestamp", 0.0))
        return entries

    def cleanup(self) -> None:
        if self.max_snapshots is None:
            return
        snapshots = self.list_snapshots()
        while len(snapshots) > self.max_snapshots:
            oldest = snapshots.pop(0)
            snapshot_id = oldest.get("snapshot_id")
            if snapshot_id:
                self.delete(snapshot_id)

    def _evict_oldest(self) -> None:
        snapshots = self.list_snapshots()
        if not snapshots:
            return
        snapshot_id = snapshots[0].get("snapshot_id")
        if snapshot_id:
            self.delete(snapshot_id)
