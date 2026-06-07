from __future__ import annotations


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict[str, object]] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        risk_level: str,
        required_capability: str,
        handler,
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "risk_level": risk_level,
            "required_capability": required_capability,
            "handler": handler,
        }

    def list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "risk_level": tool["risk_level"],
                "required_capability": tool["required_capability"],
            }
            for tool in self._tools.values()
        ]

    def resolve(self, name: str):
        return self._tools[name]["handler"]

    def metadata(self, name: str) -> dict[str, object]:
        return dict(self._tools[name])
