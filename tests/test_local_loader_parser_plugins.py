from sive.domain.parse.loader import (
    LOCAL_FORMAT_PARSER_PLUGINS,
    REMOTE_FORMAT_PARSER_PLUGINS,
    _resolve_local_format_parser,
    _resolve_remote_format_parser,
)


def test_local_format_parser_plugins_cover_required_formats():
    names = {plugin.name for plugin in LOCAL_FORMAT_PARSER_PLUGINS}

    assert {"markdown", "xlsx", "csv", "word", "pdf"}.issubset(names)


def test_remote_format_parser_plugins_cover_required_formats():
    names = {plugin.name for plugin in REMOTE_FORMAT_PARSER_PLUGINS}

    assert {"markdown", "xlsx", "csv", "word", "pdf"}.issubset(names)


def test_local_parser_resolution_handles_markdown_aliases():
    md_parser = _resolve_local_format_parser(".md")
    markdown_parser = _resolve_local_format_parser(".markdown")

    assert md_parser is not None
    assert markdown_parser is not None
    assert md_parser.name == "markdown"
    assert markdown_parser.name == "markdown"


def test_remote_parser_resolution_handles_markdown_aliases():
    md_parser = _resolve_remote_format_parser(".md")
    markdown_parser = _resolve_remote_format_parser(".markdown")

    assert md_parser is not None
    assert markdown_parser is not None
    assert md_parser.name == "markdown"
    assert markdown_parser.name == "markdown"


def test_local_parser_resolution_returns_none_for_unsupported_extension():
    assert _resolve_local_format_parser(".bin") is None


def test_remote_parser_resolution_returns_none_for_unsupported_extension():
    assert _resolve_remote_format_parser(".bin") is None
