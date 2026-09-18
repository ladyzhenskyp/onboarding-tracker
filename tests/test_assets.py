"""Every CDN asset referenced by a template must resolve.

A wrong CDN path fails silently in the browser (charts just don't draw), so CI
checks each external <script src> / <link href> with a HEAD request. Skipped
when there is no network (e.g. an offline sandbox).
"""

import re
from pathlib import Path

import httpx
import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
URL_RE = re.compile(r'(?:src|href)="(https://[^"]+)"')


def _external_urls() -> set[str]:
    urls: set[str] = set()
    for f in TEMPLATES.rglob("*.html"):
        urls.update(URL_RE.findall(f.read_text()))
    return {u for u in urls if "fonts.gstatic" not in u}


@pytest.mark.parametrize("url", sorted(_external_urls()))
def test_cdn_asset_resolves(url):
    try:
        r = httpx.head(url, follow_redirects=True, timeout=10)
    except httpx.TransportError as e:  # no network in this environment
        pytest.skip(f"network unavailable: {e}")
    assert r.status_code == 200, f"{url} -> {r.status_code}"
    ctype = r.headers.get("content-type", "")
    assert "text/html" not in ctype, f"{url} served HTML (probably a 404 page): {ctype}"
