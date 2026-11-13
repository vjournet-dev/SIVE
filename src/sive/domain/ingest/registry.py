from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import IngestMethodPlugin, IngestRequest


@dataclass
class IngestMethodRegistry:
    _plugins: list[IngestMethodPlugin] = field(default_factory=list)

    def register(self, plugin: IngestMethodPlugin) -> None:
        self._plugins.append(plugin)

    def list_names(self) -> list[str]:
        return [plugin.name for plugin in self._plugins]

    def resolve(self, request: IngestRequest) -> IngestMethodPlugin:
        for plugin in self._plugins:
            if plugin.can_handle(request):
                return plugin
        raise ValueError("No ingest method plugin can handle this source.")
