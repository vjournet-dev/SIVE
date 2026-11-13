from sive.infra.web.scraper import is_allowed_url


def test_is_allowed_url_accepts_docs_root_without_trailing_slash():
    assert is_allowed_url(
        url="https://playwright.dev/docs",
        allowed_host="playwright.dev",
        allowed_path_prefix="/docs/",
    )


def test_is_allowed_url_accepts_docs_descendants_and_rejects_outside_prefix():
    assert is_allowed_url(
        url="https://playwright.dev/docs/intro",
        allowed_host="playwright.dev",
        allowed_path_prefix="/docs/",
    )
    assert not is_allowed_url(
        url="https://playwright.dev/community/welcome",
        allowed_host="playwright.dev",
        allowed_path_prefix="/docs/",
    )
