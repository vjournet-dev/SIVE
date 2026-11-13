from sive.domain.core.sites import site_from_local_path


def test_site_from_local_path_uses_stable_path_based_id_for_directories(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    site = site_from_local_path(str(docs_dir))

    assert site.site_id.startswith("local-docs-")
    assert site.site_name == docs_dir.resolve().as_posix()
    assert site.allowed_host == "local"
    assert site.allowed_path_prefix == "/"


def test_site_from_local_path_avoids_collisions_for_same_directory_name(tmp_path):
    first_dir = tmp_path / "team-a" / "docs"
    second_dir = tmp_path / "team-b" / "docs"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)

    first_site = site_from_local_path(str(first_dir))
    second_site = site_from_local_path(str(second_dir))

    assert first_site.site_id != second_site.site_id
    assert first_site.site_id.startswith("local-docs-")
    assert second_site.site_id.startswith("local-docs-")