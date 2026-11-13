from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import FormatParserPlugin


@dataclass
class FormatParserRegistry:
    _plugins: list[FormatParserPlugin] = field(default_factory=list)

    def register(self, plugin: FormatParserPlugin) -> None:
        self._plugins.append(plugin)

    def list_names(self) -> list[str]:
        return [plugin.name for plugin in self._plugins]

    def resolve(self, source: str, metadata: dict[str, object] | None = None) -> FormatParserPlugin:
        for plugin in self._plugins:
            if plugin.can_handle(source, metadata):
                return plugin
        raise ValueError("No format parser plugin can handle this source.")
