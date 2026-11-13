from sive.domain.index import indexing as indexer


def test_resolve_chunk_strategy_for_known_source_kinds():
    assert indexer._resolve_chunk_strategy("markdown").name == "markdown"
    assert indexer._resolve_chunk_strategy("csv").name == "table"
    assert indexer._resolve_chunk_strategy("xlsx").name == "table"
    assert indexer._resolve_chunk_strategy("pdf").name == "pdf"
    assert indexer._resolve_chunk_strategy("docx").name == "word"


def test_resolve_chunk_strategy_falls_back_to_generic():
    assert indexer._resolve_chunk_strategy("unknown").name == "generic"


def test_table_chunk_strategy_disables_overlap_duplication():
    strategy = indexer._resolve_chunk_strategy("csv")
    text = "x" * 2100

    chunks = strategy.chunk(text, chunk_size=1000, overlap=200)

    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 100


def test_pdf_chunk_strategy_caps_overlap_for_stability():
    strategy = indexer._resolve_chunk_strategy("pdf")
    text = "x" * 2600

    chunks = strategy.chunk(text, chunk_size=1200, overlap=500)

    assert len(chunks) == 3
    # 1200 // 6 = 200, so second chunk starts at 1000
    assert chunks[1][0] == "x"
    assert len(chunks[1]) == 1200
