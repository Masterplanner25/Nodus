"""Execution sessions for the Nodus runtime server."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

from nodus.support.config import MAX_SESSIONS, SESSION_TIMEOUT_MS
from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE, MemoryStore
from nodus.vm.vm import VM


@dataclass
class Session:
    id: str
    vm: VM
    created_time: float
    last_access: float
    execution_count: int = 0
    import_state: dict | None = None


class SessionManager:
    def __init__(self, *, timeout_ms: int = SESSION_TIMEOUT_MS, max_sessions: int = MAX_SESSIONS):
        self.timeout_ms = timeout_ms
        self.max_sessions = max_sessions
        self.sessions: dict[str, Session] = {}

    def _is_expired(self, last_access: float, now: float) -> bool:
        if self.timeout_ms is None:
            return False
        grace_ms = min(10.0, self.timeout_ms * 0.2)
        return (now - last_access) * 1000.0 > (self.timeout_ms + grace_ms)

    def create(self, vm: VM) -> Session:
        self.cleanup()
        if len(self.sessions) >= self.max_sessions:
            self._evict_oldest()
        session_id = secrets.token_hex(16)
        now = time.monotonic()
        session = Session(
            id=session_id,
            vm=vm,
            created_time=now,
            last_access=now,
            execution_count=0,
            import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
        )
        vm.session_id = session_id
        if not isinstance(getattr(vm, "memory_store", None), MemoryStore) or vm.memory_store is GLOBAL_MEMORY_STORE:
            vm.memory_store = MemoryStore()
        self.sessions[session_id] = session
        return session

    def create_from_state(self, state: dict, import_state: dict | None = None) -> Session:
        vm = VM([], {}, code_locs=[], source_path=None)
        vm.memory_store = MemoryStore()
        vm.import_state(state)
        session = self.create(vm)
        session.import_state = import_state or {"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None}
        return session

    def get(self, session_id: str) -> Session | None:
        self.cleanup()
        return self.sessions.get(session_id)

    def touch(self, session: Session) -> None:
        session.last_access = time.monotonic()

    def record_execution(self, session: Session) -> None:
        session.execution_count += 1
        self.touch(session)

    def cleanup(self) -> None:
        if self.timeout_ms is None:
            return
        now = time.monotonic()
        expired = []
        for session_id, session in self.sessions.items():
            if self._is_expired(session.last_access, now):
                expired.append(session_id)
        for session_id in expired:
            self.sessions.pop(session_id, None)

    def list_sessions(self) -> list[dict]:
        self.cleanup()
        out = []
        for session in self.sessions.values():
            out.append(
                {
                    "id": session.id,
                    "created_time": session.created_time,
                    "last_access": session.last_access,
                    "execution_count": session.execution_count,
                }
            )
        return out

    def _evict_oldest(self) -> None:
        if not self.sessions:
            return
        oldest_id = min(self.sessions.items(), key=lambda item: item[1].last_access)[0]
        self.sessions.pop(oldest_id, None)
