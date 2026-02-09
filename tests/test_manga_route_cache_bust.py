import asyncio
from types import SimpleNamespace

from app.routes.manga import (
    _to_public_data_url,
    _with_mtime_query,
    get_chapter_details,
    list_manga,
)


def test_with_mtime_query_appends_version(tmp_path):
    image = tmp_path / "1.jpg"
    image.write_bytes(b"ok")

    result = _with_mtime_query("/data/manga/ch1/1.jpg", image)

    assert result.startswith("/data/manga/ch1/1.jpg?v=")


def test_get_chapter_details_original_url_has_cache_bust(tmp_path):
    data_dir = tmp_path / "data" / "raw"
    chapter_dir = data_dir / "manga-a" / "chapter-1"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    image = chapter_dir / "1.jpg"
    image.write_bytes(b"img")

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = SimpleNamespace(data_dir=str(data_dir), output_dir=str(output_dir))

    payload = asyncio.run(get_chapter_details("manga-a", "chapter-1", settings))

    assert payload["pages"][0]["name"] == "1.jpg"
    assert payload["pages"][0]["original_url"].startswith(
        "/data/raw/manga-a/chapter-1/1.jpg?v="
    )


def test_to_public_data_url_adds_raw_prefix(tmp_path):
    data_dir = tmp_path / "data" / "raw"
    image = data_dir / "manga-b" / "chapter-2" / "8.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"img")

    assert (
        _to_public_data_url(image, data_dir)
        == "/data/raw/manga-b/chapter-2/8.jpg"
    )


def test_list_manga_cover_url_uses_real_file_path(tmp_path):
    data_dir = tmp_path / "data" / "raw"
    chapter_dir = data_dir / "manga-c" / "chapter-1"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "1.jpg").write_bytes(b"img")
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = SimpleNamespace(data_dir=str(data_dir), output_dir=str(output_dir))
    mangas = asyncio.run(list_manga(settings))

    assert len(mangas) == 1
    assert mangas[0].cover_url == "/data/raw/manga-c/chapter-1/1.jpg"
