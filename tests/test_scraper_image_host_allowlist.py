from app.routes.scraper import _is_allowed_image_host


def test_allowlist_allows_site_domains_and_subdomains():
    assert _is_allowed_image_host("https://toongod.org/c.jpg", "https://toongod.org")
    assert _is_allowed_image_host(
        "https://img.toongod.org/c.jpg", "https://toongod.org"
    )
    assert _is_allowed_image_host(
        "https://mangaforfree.com/c.jpg", "https://mangaforfree.com"
    )


def test_allowlist_allows_wp_cdn_wrapped_site_image():
    assert _is_allowed_image_host(
        "https://i0.wp.com/mangaforfree.com/wp-content/uploads/a.jpg",
        "https://mangaforfree.com",
    )


def test_allowlist_blocks_unrelated_domains():
    assert not _is_allowed_image_host(
        "https://cdn.example.com/cover.jpg", "https://toongod.org"
    )
