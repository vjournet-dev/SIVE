from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


def normalize_topic(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9.+#-]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def find_best_topic_route(
    routes: dict[str, Any],
    query: str,
    topic: str | None,
) -> Any | None:
    if topic:
        explicit_key = normalize_topic(topic)
        if explicit_key:
            return routes.get(explicit_key)

    normalized_query = normalize_topic(query)
    if not normalized_query:
        return None

    matching = [
        route
        for route in routes.values()
        if route.topic_key
        and re.search(rf"(?<![a-z0-9]){re.escape(route.topic_key)}(?![a-z0-9])", normalized_query)
    ]
    if not matching:
        return None

    return max(matching, key=lambda route: len(route.topic_key))


def find_named_site_ids(query: str, sites: Iterable[Any]) -> tuple[str, ...]:
    normalized_query = normalize_topic(query)
    if not normalized_query:
        return ()

    matching: list[tuple[int, str]] = []
    for site in sites:
        site_id = str(site.site_id).strip()
        site_name = str(site.site_name).strip()
        terms = {normalize_topic(site_id), normalize_topic(site_name)} - {""}
        specificity = max(
            (
                len(term)
                for term in terms
                if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized_query)
            ),
            default=0,
        )
        if specificity:
            matching.append((specificity, site_id))

    matching.sort(key=lambda item: (-item[0], item[1]))
    return tuple(dict.fromkeys(site_id for _, site_id in matching))
