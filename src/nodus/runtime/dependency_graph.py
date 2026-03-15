"""Persistent runtime dependency graph for incremental module compilation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from nodus.tooling.project import NODUS_DIRNAME


DEPS_FILENAME = "deps.json"


@dataclass
class DependencyNode:
    module_path: str
    imported_modules: list[str]
    last_compiled_mtime: int

    def to_dict(self) -> dict[str, object]:
        return {
            "imports": list(self.imported_modules),
            "mtime": self.last_compiled_mtime,
        }


class DependencyGraph:
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
        self.modules: dict[str, DependencyNode] = {}

    @property
    def path(self) -> str:
        return os.path.join(self.project_root, NODUS_DIRNAME, DEPS_FILENAME)

    def get(self, module_path: str) -> DependencyNode | None:
        return self.modules.get(os.path.abspath(module_path))

    def update_module(self, module_path: str, imported_modules: list[str], last_compiled_mtime: int) -> None:
        normalized = os.path.abspath(module_path)
        self.modules[normalized] = DependencyNode(
            module_path=normalized,
            imported_modules=sorted(os.path.abspath(path) for path in imported_modules),
            last_compiled_mtime=int(last_compiled_mtime),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "modules": {
                path: self.modules[path].to_dict()
                for path in sorted(self.modules)
            }
        }

    def save(self) -> None:
        nodus_dir = os.path.join(self.project_root, NODUS_DIRNAME)
        os.makedirs(nodus_dir, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, sort_keys=True)
            handle.write("\n")

    @classmethod
    def load(cls, project_root: str | None) -> "DependencyGraph | None":
        if project_root is None:
            return None
        graph = cls(project_root)
        if not os.path.isfile(graph.path):
            return graph
        try:
            with open(graph.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return graph
        modules = payload.get("modules", {}) if isinstance(payload, dict) else {}
        if not isinstance(modules, dict):
            return graph
        for raw_path, raw_node in modules.items():
            if not isinstance(raw_path, str) or not isinstance(raw_node, dict):
                continue
            imports = raw_node.get("imports", [])
            mtime = raw_node.get("mtime", 0)
            if not isinstance(imports, list):
                continue
            graph.modules[os.path.abspath(raw_path)] = DependencyNode(
                module_path=os.path.abspath(raw_path),
                imported_modules=sorted(os.path.abspath(str(path)) for path in imports),
                last_compiled_mtime=int(mtime),
            )
        return graph
