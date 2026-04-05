import hashlib
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.scraper.parsers.generic import (
    auto_detect_selector,
    extract_vacancies,
)

logger = logging.getLogger(__name__)

@dataclass
class VacancyItem:
    title: str
    url: str | None
    hash: str = field(init=False)

    def __post_init__(self) -> None:
        # Normalize before hashing to avoid false positives
        # from whitespace or case differences
        normalized = " ".join(self.title.lower().split())
        self.hash = hashlib.md5(normalized.encode()).hexdigest()

    def matches_keywords(self, keywords: list[str]) -> bool:
        """Check if vacancy title contains any of the keywords."""
        if not keywords:
            return True
        text = self.title.lower()
        return any(kw.lower() in text for kw in keywords)

    def absolute_url(self, base_url: str) -> str | None:
        """Resolve relative URL to absolute."""
        if not self.url:
            return None
        if self.url.startswith("http"):
            return self.url
        return urljoin(base_url, self.url)

@dataclass
class DiffResult:
    new_vacancies: list[VacancyItem]
    removed_count: int
    selector_used: str | None
    page_hash_changed: bool

    @property
    def has_new(self) -> bool:
        return len(self.new_vacancies) > 0

class DiffEngine:

    def __init__(self, css_selector: str | None = None) -> None:
        self.css_selector = css_selector

    def compute_page_hash(self, html: str) -> str:
        """
        Hash only meaningful content — strip scripts, styles,
        and dynamic attributes that change on every load.
        """
        soup = BeautifulSoup(html, "lxml")

        # Remove noise elements
        for tag in soup.select("script, style, noscript, meta, iframe, svg"):
            tag.decompose()

        # Remove dynamic attributes
        dynamic_attrs = [
            "data-token", "data-session", "data-time",
            "nonce", "data-reactid", "data-v-",
        ]
        for tag in soup.find_all(True):
            for attr in dynamic_attrs:
                # Remove exact match or prefix match
                keys_to_remove = [
                    k for k in list(tag.attrs.keys())
                    if k == attr or k.startswith(attr)
                ]
                for k in keys_to_remove:
                    del tag.attrs[k]

        content = soup.get_text(separator=" ", strip=True)
        normalized = re.sub(r"\s+", " ", content).lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def extract(self, html: str) -> tuple[list[VacancyItem], str | None]:
        """
        Extract vacancies from HTML.
        Auto-detects selector if not set.
        Returns (vacancies, selector_used).
        """
        selector = self.css_selector

        if not selector:
            selector = auto_detect_selector(html)

        if not selector:
            logger.warning("No selector found — page may be empty or need SPA fetch")
            return [], None

        raw = extract_vacancies(html, selector)
        vacancies = [
            VacancyItem(title=v["title"], url=v["url"])
            for v in raw
        ]
        return vacancies, selector

    def compare(
        self,
        html: str,
        known_hashes: set[str],
        previous_page_hash: str | None = None,
    ) -> DiffResult:
        """
        Main comparison method.

        Args:
            html: Freshly fetched HTML
            known_hashes: Set of vacancy hashes already in DB
            previous_page_hash: Last stored page hash

        Returns:
            DiffResult with new vacancies and metadata
        """
        current_vacancies, selector = self.extract(html)
        current_hashes = {v.hash for v in current_vacancies}
        new_page_hash = self.compute_page_hash(html)

        # Vacancies whose hash is not in DB yet
        new_vacancies = [
            v for v in current_vacancies
            if v.hash not in known_hashes
        ]

        # Vacancies that disappeared (closed positions)
        removed_count = len(known_hashes - current_hashes)

        page_hash_changed = (
            previous_page_hash is not None
            and new_page_hash != previous_page_hash
        )

        if new_vacancies:
            logger.info(
                f"Found {len(new_vacancies)} new vacancies "
                f"(selector: {selector})"
            )
        if removed_count:
            logger.info(f"{removed_count} vacancies disappeared")

        return DiffResult(
            new_vacancies=new_vacancies,
            removed_count=removed_count,
            selector_used=selector,
            page_hash_changed=page_hash_changed,
        )