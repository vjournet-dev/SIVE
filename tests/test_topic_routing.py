from sive.domain.routing import find_best_topic_route, normalize_topic
from sive.domain.runtime_state.state import TopicRouteRecord


def _route(topic: str, site_id: str) -> TopicRouteRecord:
    return TopicRouteRecord(
        topic=topic,
        topic_key=normalize_topic(topic),
        site_id=site_id,
        site_name=site_id,
        start_url=f"https://example.com/{site_id}",
        created_at="2026-07-21T00:00:00+00:00",
        updated_at="2026-07-21T00:00:00+00:00",
    )


def test_normalize_topic_preserves_common_technical_tokens():
    assert normalize_topic("Node.js Streams") == "node.js streams"
    assert normalize_topic("C++ Memory") == "c++ memory"
    assert normalize_topic("C# Async") == "c# async"
    assert normalize_topic(".NET Hosting") == ".net hosting"


def test_find_best_topic_route_avoids_substring_false_positive():
    routes = {
        "react": _route("react", "react-docs"),
        "react-native": _route("react-native", "react-native-docs"),
    }

    result = find_best_topic_route(routes, query="How does reactive caching work?", topic=None)

    assert result is None


def test_find_best_topic_route_matches_technical_terms_with_boundaries():
    routes = {
        "node.js": _route("node.js", "nodejs-docs"),
        ".net": _route(".NET", "dotnet-docs"),
    }

    node_result = find_best_topic_route(routes, query="How do node.js streams handle backpressure?", topic=None)
    dotnet_result = find_best_topic_route(routes, query="How does .NET hosting work?", topic=None)

    assert node_result is not None
    assert node_result.site_id == "nodejs-docs"
    assert dotnet_result is not None
    assert dotnet_result.site_id == "dotnet-docs"