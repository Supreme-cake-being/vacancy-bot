# Placeholder for SPA-specific parsing logic.
# Currently fetch_spa_html in fetcher.py handles JS rendering,
# and generic.py handles content extraction.
# Add site-specific overrides here if needed.

SPA_SITES = {
    # "jobs.example.com": ".custom-job-selector",
}


def get_selector_override(url: str) -> str | None:
    """
    Return a hardcoded selector for known SPA sites.
    Falls back to auto-detection in generic.py if None.
    """
    for domain, selector in SPA_SITES.items():
        if domain in url:
            return selector
    return None