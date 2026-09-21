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
# Only assets the page loads (<script>, <link>), not ordinary links a visitor may click.
URL_RE = re.compile(r'<(?:script|link)\b[^>]*?(?:src|href)="(https://[^"]+)"')


def test_only_the_font_is_loaded_from_another_site():
    """Scripts and styles are served by the app itself; the Switzer font is the one exception."""
    hosts = {u.split("/")[2] for u in _external_urls()}
    assert hosts <= {"api.fontshare.com"}, hosts


def test_compiled_tailwind_matches_the_templates():
    """Fails when a template uses a new class and scripts/build_css.py was not run again."""
    import importlib.util

    root = TEMPLATES.parent.parent
    spec = importlib.util.spec_from_file_location("build_css", root / "scripts" / "build_css.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    first_line = (root / "app" / "static" / "vendor" / "tailwind.css").read_text().splitlines()[0]
    assert f"sources:{mod.source_hash()}" in first_line, "run: python scripts/build_css.py"


def test_vendored_scripts_are_served(client):
    for path in (
        "/static/vendor/tailwind.css",
        "/static/vendor/htmx-2.0.4.min.js",
        "/static/vendor/chart-4.4.1.umd.js",
    ):
        assert client.get(path).status_code == 200, path


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
