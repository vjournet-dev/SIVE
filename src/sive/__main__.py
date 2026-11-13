from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

from .config import (
    CHROMA_DIR,
    DEFAULT_ALLOWED_HOST,
    DEFAULT_ALLOWED_PATH_PREFIX,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_SITE_ID,
    DEFAULT_SITE_NAME,
    DEFAULT_START_URL,
    site_index_state_path,
    site_raw_docs_path,
)
from .domain.client_install.service import (
    install_client_mcp_configs,
    install_skill_files,
    install_skill_files_default_locations,
)
from .domain.core.sites import SiteDefinition
from .domain.index.indexing import index_chunks, index_pages_incrementally, make_chunks
from .domain.ingest.service import load_pages_for_site, run_ingest_for_site
from .infra.web.scraper import load_pages_jsonl, save_pages_jsonl


def _iter_sites(args: argparse.Namespace) -> Iterable[SiteDefinition]:
    additional_start_urls = tuple(args.additional_start_url or ())
    additional_path_prefixes = tuple(args.additional_allowed_path_prefix or ())
    return [
        SiteDefinition(
            site_id=args.site_id,
            site_name=args.site_name,
            start_url=args.start_url,
            allowed_host=args.allowed_host,
            allowed_path_prefix=args.allowed_path_prefix,
            start_urls=(args.start_url, *additional_start_urls),
            allowed_path_prefixes=(args.allowed_path_prefix, *additional_path_prefixes),
        )
    ]


def cmd_scrape(args: argparse.Namespace) -> None:
    summaries: list[str] = []
    for site in _iter_sites(args):
        print(f"[scrape] Start: {site.site_name} ({site.site_id}) -> {site.start_url}")
        pages = load_pages_for_site(
            site,
            max_pages=args.max_pages,
            delay=args.delay,
            crawl_progress_every=25,
            progress_callback=None,
        )
        output_path = site_raw_docs_path(site.site_id)
        save_pages_jsonl(pages, output_path)
        print(f"[scrape] Saved: {len(pages)} pages in {output_path}")
        summaries.append(f"{site.site_name} ({site.site_id}): {len(pages)} pages -> {output_path}")
    print("Scrape complete:\n" + "\n".join(summaries))


def cmd_index(args: argparse.Namespace) -> None:
    summaries: list[str] = []
    reset_collection = args.reset
    for site in _iter_sites(args):
        print(f"[index] Start: {site.site_name} ({site.site_id})")
        pages = load_pages_jsonl(site_raw_docs_path(site.site_id))
        print(f"[index] Loaded raw pages: {len(pages)}")
        if args.incremental:
            result = index_pages_incrementally(
                pages=pages,
                chroma_dir=CHROMA_DIR,
                collection_name=args.collection,
                state_path=site_index_state_path(site.site_id),
                reset_collection=reset_collection,
                embedding_model_name=args.embedding_model,
                chunk_size=args.chunk_size,
                overlap=args.chunk_overlap,
            )
            summaries.append(
                f"{site.site_name} ({site.site_id}): {result.changed_pages} changed, {result.removed_pages} removed, "
                f"{result.skipped_pages} skipped, {result.indexed_chunks} chunks upserted"
            )
        else:
            chunks = make_chunks(pages, chunk_size=args.chunk_size, overlap=args.chunk_overlap)
            print(f"[index] Generated chunks: {len(chunks)}")
            count = index_chunks(
                chunks=chunks,
                chroma_dir=CHROMA_DIR,
                collection_name=args.collection,
                reset_collection=reset_collection,
                embedding_model_name=args.embedding_model,
            )
            print(f"[index] Upserted chunks: {count}")
            summaries.append(f"{site.site_name} ({site.site_id}): {count} chunks indexed")
        reset_collection = False
    print("Index complete:\n" + "\n".join(summaries))


def cmd_ingest(args: argparse.Namespace) -> None:
    summaries: list[str] = []
    reset_collection = args.reset
    for site in _iter_sites(args):
        print(f"[ingest] Start: {site.site_name} ({site.site_id}) -> {site.start_url}")
        result = run_ingest_for_site(
            site,
            incremental=args.incremental,
            max_pages=args.max_pages,
            delay=args.delay,
            collection_name=args.collection,
            embedding_model_name=args.embedding_model,
            reset_collection=reset_collection,
            chunk_size=args.chunk_size,
            overlap=args.chunk_overlap,
        )
        summaries.append(
            f"{result.site_name} ({result.site_id}): {result.pages_scraped} pages scraped, "
            f"{result.changed_pages} changed, {result.removed_pages} removed, "
            f"{result.skipped_pages} skipped, {result.indexed_chunks} chunks upserted"
        )
        print(
            "[ingest] Done: "
            f"{result.pages_scraped} pages, {result.indexed_chunks} chunks, {result.duration_seconds:.1f}s"
        )
        reset_collection = False
    print("Ingest complete:\n" + "\n".join(summaries))


def cmd_install(args: argparse.Namespace) -> None:
    if args.output_dir:
        written = install_skill_files(args.target, Path(args.output_dir))
        mcp_written = install_client_mcp_configs(
            args.target,
            Path(args.output_dir),
            python_executable=args.python_executable,
            cwd=args.mcp_cwd,
        )
        print("Install complete (custom output-dir):")
        for path in written:
            print(f"- {path}")
        print("MCP client config snippets:")
        for path in mcp_written:
            print(f"- {path}")
        return

    written_by_target = install_skill_files_default_locations(args.target)
    print("Install complete (default locations):")
    for target, paths in written_by_target.items():
        print(f"[{target}]")
        for path in paths:
            print(f"- {path}")

    print(
        "Note: des fichiers MCP_SERVER.json (ou sive.mcp.json) ont ete installes avec le Python/CWD detectes."
    )


def cmd_serve(_args: argparse.Namespace) -> None:
    # Import lazily so help/install paths do not require heavy runtime deps at startup.
    from .app.mcp_server import run_server

    run_server()


def build_parser() -> argparse.ArgumentParser:
    formatter = argparse.ArgumentDefaultsHelpFormatter
    parser = argparse.ArgumentParser(
        prog="sive",
        description="SIVE (Scrap Ingest Vectorize Extends)",
        formatter_class=formatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    crawl_common = argparse.ArgumentParser(add_help=False, formatter_class=formatter)
    crawl_common.add_argument(
        "--start-url",
        default=DEFAULT_START_URL,
        help="URL de depart du crawl ou chemin local (html, docx, json, pdf, ou dossier).",
    )
    crawl_common.add_argument(
        "--additional-start-url",
        action="append",
        default=[],
        help="URL de depart supplementaire sur le meme host (option repetable).",
    )
    crawl_common.add_argument(
        "--allowed-host",
        default=DEFAULT_ALLOWED_HOST,
        help="Host autorise pendant le crawl (les autres domaines sont ignores).",
    )
    crawl_common.add_argument(
        "--allowed-path-prefix",
        default=DEFAULT_ALLOWED_PATH_PREFIX,
        help="Prefixe de chemin autorise pendant le crawl (ex: /docs/).",
    )
    crawl_common.add_argument(
        "--additional-allowed-path-prefix",
        action="append",
        default=[],
        help="Prefixe de chemin autorise supplementaire (option repetable).",
    )
    crawl_common.add_argument(
        "--max-pages",
        type=int,
        default=1200,
        help="Nombre maximum de pages a crawler pour le site cible.",
    )
    crawl_common.add_argument(
        "--delay",
        type=float,
        default=0.2,
        help="Delai (en secondes) entre deux requetes HTTP pour limiter la charge.",
    )

    site_common = argparse.ArgumentParser(add_help=False, formatter_class=formatter)
    site_common.add_argument(
        "--site-id",
        default=DEFAULT_SITE_ID,
        help="Identifiant technique du site (utilise dans les metadonnees et filtres de recherche).",
    )
    site_common.add_argument(
        "--site-name",
        default=DEFAULT_SITE_NAME,
        help="Nom lisible du site (expose dans les resultats MCP).",
    )

    index_common = argparse.ArgumentParser(add_help=False, formatter_class=formatter)
    index_common.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help="Nom de la collection Chroma qui stocke les chunks de documentation.",
    )
    index_common.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Taille cible d'un chunk de texte avant overlap.",
    )
    index_common.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Nombre de caracteres partages entre deux chunks consecutifs.",
    )
    index_common.add_argument(
        "--embedding-model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Modele SentenceTransformers utilise pour vectoriser les chunks.",
    )
    index_common.add_argument(
        "--reset",
        action="store_true",
        help="Supprime la collection cible avant indexation (reindexation complete).",
    )
    index_common.add_argument(
        "--incremental",
        action="store_true",
        help="Indexe uniquement les pages modifiees et supprime les pages disparues.",
    )

    scrape = sub.add_parser(
        "scrape",
        parents=[crawl_common, site_common],
        help="Crawler la documentation et sauvegarder en JSONL brut",
        description="Crawl un ou plusieurs sites de documentation et ecrit les pages brutes dans data/raw.",
        formatter_class=formatter,
    )
    scrape.set_defaults(func=cmd_scrape)

    index = sub.add_parser(
        "index",
        parents=[index_common, site_common],
        help="Indexer les pages brutes dans Chroma",
        description="Charge les JSONL deja scrapes et les indexe dans la base vectorielle Chroma.",
        formatter_class=formatter,
    )
    index.set_defaults(func=cmd_index)

    ingest = sub.add_parser(
        "ingest",
        parents=[crawl_common, index_common, site_common],
        help="Enchainer scrape puis index en une seule commande",
        description="Execute le crawl web ou le chargement d'une source locale, puis l'indexation vectorielle.",
        formatter_class=formatter,
    )
    ingest.set_defaults(func=cmd_ingest)

    serve = sub.add_parser(
        "serve",
        help="Lancer le serveur MCP sur stdio",
        description="Expose les outils MCP de recherche documentaire sur le transport stdio.",
        formatter_class=formatter,
    )
    serve.set_defaults(func=cmd_serve)

    install = sub.add_parser(
        "install",
        help="Installer les prompts/skills /sive pour differents clients LLM",
        description="Installe les fichiers de skill/prompt /sive pour Claude, Copilot, GPT et Gemini.",
        formatter_class=formatter,
    )
    install.add_argument(
        "--target",
        default="all",
        choices=["all", "claude", "copilot", "gpt", "gemini", "mistral", "microsoft-cowork"],
        help="Client cible a installer.",
    )
    install.add_argument(
        "--output-dir",
        default=None,
        help="Repertoire de sortie explicite (desactive les emplacements par defaut clients).",
    )
    install.add_argument(
        "--python-executable",
        default=None,
        help="Python a ecrire dans la config MCP (sinon utilise l'executable sive detecte).",
    )
    install.add_argument(
        "--mcp-cwd",
        default=None,
        help="CWD a ecrire dans la config MCP (par defaut: dossier de l'executable configure).",
    )
    install.set_defaults(func=cmd_install)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
