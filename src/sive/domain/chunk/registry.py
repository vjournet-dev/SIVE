from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ChunkStrategy


@dataclass
class ChunkStrategyRegistry:
    _strategies: dict[str, ChunkStrategy] = field(default_factory=dict)
    _default: ChunkStrategy | None = None

    def register(self, format_name: str, strategy: ChunkStrategy) -> None:
        self._strategies[format_name.strip().lower()] = strategy

    def register_many(self, format_names: list[str], strategy: ChunkStrategy) -> None:
        for format_name in format_names:
            self.register(format_name, strategy)

    def set_default(self, strategy: ChunkStrategy) -> None:
        self._default = strategy

    def list_formats(self) -> list[str]:
        return sorted(self._strategies.keys())

    def resolve(self, format_name: str) -> ChunkStrategy:
        key = format_name.strip().lower()
        strategy = self._strategies.get(key)
        if strategy is not None:
            return strategy
        if self._default is not None:
            return self._default
        raise ValueError(f"No chunk strategy registered for format '{format_name}'.")
