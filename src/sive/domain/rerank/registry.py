from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import RerankStrategy


@dataclass
class RerankStrategyRegistry:
    _strategies: dict[str, RerankStrategy] = field(default_factory=dict)
    _default: RerankStrategy | None = None

    def register(self, format_name: str, strategy: RerankStrategy) -> None:
        self._strategies[format_name.strip().lower()] = strategy

    def register_many(self, format_names: list[str], strategy: RerankStrategy) -> None:
        for format_name in format_names:
            self.register(format_name, strategy)

    def set_default(self, strategy: RerankStrategy) -> None:
        self._default = strategy

    def list_formats(self) -> list[str]:
        return sorted(self._strategies.keys())

    def resolve(self, format_name: str) -> RerankStrategy:
        key = format_name.strip().lower()
        strategy = self._strategies.get(key)
        if strategy is not None:
            return strategy
        if self._default is not None:
            return self._default
        raise ValueError(f"No rerank strategy registered for format '{format_name}'.")
