from scraper.challenge import looks_like_challenge


def test_cloudflare_marker_lowercase():
    html = "<div>cloudflare ray id</div>"
    assert looks_like_challenge(html)
