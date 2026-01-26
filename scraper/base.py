from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Sequence
import random
import re
from urllib.parse import urljoin


DEFAULT_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
)


@dataclass(frozen=True)
class Manga:
    id: str
    title: str
    url: str | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    url: str | None = None
    index: int | None = None


@dataclass
class ScraperConfig:
    base_url: str
    headless: bool = True
    timeout_ms: int = 30000
    scroll_step: int = 900
    scroll_wait_ms: int = 650
    scroll_max_idle: int = 6
    challenge_wait_ms: int = 15000
    challenge_poll_ms: int = 1000
    http_mode: bool = False
    http_timeout_sec: int = 25
    user_agent: str | None = None
    override_user_agent: bool = True
    manual_challenge: bool = False
    user_agents: Sequence[str] = field(
        default_factory=lambda: list(DEFAULT_USER_AGENTS)
    )
    browser_channel: str | None = None
    user_data_dir: str | None = None
    storage_state_path: str | None = None
    cookies: dict[str, str] | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)


class UserAgentPool:
    def __init__(self, user_agents: Sequence[str] | None = None) -> None:
        self._user_agents = (
            list(user_agents) if user_agents else list(DEFAULT_USER_AGENTS)
        )

    def pick(self) -> str:
        return random.choice(self._user_agents)


def safe_name(value: str, default: str = "manga") -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned or default


def normalize_url(base_url: str, url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urljoin(base_url, url)


def load_storage_state_cookies(
    storage_state_path: str | None, domain_filter: str | None = None
) -> dict[str, str]:
    if not storage_state_path:
        return {}
    path = Path(storage_state_path)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    cookies = payload.get("cookies", []) if isinstance(payload, dict) else []
    result: dict[str, str] = {}
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        domain = cookie.get("domain")
        if not name or value is None:
            continue
        if domain_filter and domain and domain_filter not in domain:
            continue
        result[str(name)] = str(value)
    return result


class BaseScraper(ABC):
    def __init__(self, config: ScraperConfig) -> None:
        self.config = config
        self.user_agent_pool = UserAgentPool(config.user_agents)

    @abstractmethod
    async def search_manga(self, keyword: str) -> Sequence[Manga]:
        """Search manga by keyword."""

    @abstractmethod
    async def get_chapters(self, manga: Manga) -> Sequence[Chapter]:
        """Fetch chapter metadata for a manga."""

    @abstractmethod
    async def download_images(
        self, manga: Manga, chapter: Chapter, output_root: Path
    ) -> Any:
        """Download chapter images into output_root."""

    async def list_catalog(
        self,
        page: int = 1,
        orderby: str | None = None,
        *,
        path: str | None = None,
    ) -> Sequence[Manga] | tuple[Sequence[Manga], bool]:
        """Optional: list catalog items from site index."""
        raise NotImplementedError
