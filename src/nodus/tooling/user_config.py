"""User-level configuration for Nodus tooling.

Stores credentials and preferences in ~/.nodus/config.toml.

SECURITY NOTE: This file contains registry tokens and should NOT be
committed to version control. Add ~/.nodus/ to your .gitignore.
"""
from __future__ import annotations

import os
from pathlib import Path

# tomllib is stdlib in Python 3.11+; tomli is the backport for 3.10
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-reuse-import]


_NODUS_DIR = Path.home() / ".nodus"
_CONFIG_PATH = _NODUS_DIR / "config.toml"


class UserConfig:
    """Read/write ~/.nodus/config.toml for user-level Nodus settings."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or _CONFIG_PATH
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        """Load config file if it exists. Silently ignore if missing."""
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    self._data = tomllib.load(f)
            except Exception:
                self._data = {}

    def get_registry_token(self, registry_url: str | None = None) -> str | None:
        """
        Return the token for the given registry URL.
        Falls back to the global default token if no URL-specific token exists.
        Returns None if no token is configured.
        """
        registry_section = self._data.get("registry", {})
        if registry_url and isinstance(registry_section, dict):
            url_section = registry_section.get(registry_url, {})
            if isinstance(url_section, dict):
                token = url_section.get("token")
                if token:
                    return str(token)
        if isinstance(registry_section, dict):
            token = registry_section.get("token")
            if token:
                return str(token)
        return None

    def set_registry_token(self, token: str, registry_url: str | None = None) -> None:
        """Store token for registry URL (or global default) and persist to disk."""
        if "registry" not in self._data:
            self._data["registry"] = {}
        registry_section = self._data["registry"]
        if registry_url:
            if registry_url not in registry_section:
                registry_section[registry_url] = {}
            registry_section[registry_url]["token"] = token
        else:
            registry_section["token"] = token
        self.save()

    def clear_registry_token(self, registry_url: str | None = None) -> None:
        """Remove token for registry URL (or global default)."""
        registry_section = self._data.get("registry", {})
        if not isinstance(registry_section, dict):
            return
        if registry_url:
            url_section = registry_section.get(registry_url, {})
            if isinstance(url_section, dict):
                url_section.pop("token", None)
                if not url_section:
                    registry_section.pop(registry_url, None)
        else:
            registry_section.pop("token", None)
        self.save()

    def save(self) -> None:
        """Write config to disk, creating ~/.nodus/ directory if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        registry = self._data.get("registry", {})
        if isinstance(registry, dict):
            global_token = registry.get("token")
            url_entries = {k: v for k, v in registry.items() if k != "token" and isinstance(v, dict)}
            if global_token or url_entries:
                lines.append("[registry]")
                if global_token:
                    lines.append(f'token = "{_escape_toml(str(global_token))}"')
                lines.append("")
                for url, url_cfg in url_entries.items():
                    token = url_cfg.get("token")
                    if token:
                        lines.append(f'[registry."{_escape_toml(url)}"]')
                        lines.append(f'token = "{_escape_toml(str(token))}"')
                        lines.append("")
        text = "\n".join(lines).strip()
        if text:
            text += "\n"
        with open(self._path, "w", encoding="utf-8") as f:
            f.write(text)


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
