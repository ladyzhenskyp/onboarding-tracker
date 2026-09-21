"""Rebuild app/static/vendor/tailwind.css from the classes used in the templates.

Run this after adding a Tailwind class that was not used before:

    python scripts/build_css.py

It needs Node (npx). The output is committed, so the running app and the Docker
image need neither Node nor a CDN. A test (tests/test_assets.py) fails when the
templates changed and this file was not rebuilt.
"""

import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "vendor" / "tailwind.css"
TEMPLATES = ROOT / "app" / "templates"
OTHER = [ROOT / "app" / "static" / "app.js", ROOT / "tailwind.config.js"]
TAILWIND = "tailwindcss@3.4.17"


def source_hash() -> str:
    """Fingerprint of what decides the CSS: class names in the templates, app.js, the config.

    Editing the wording of a page does not change it; using a new class does.
    """
    classes: set[str] = set()
    for f in TEMPLATES.rglob("*.html"):
        for attr in re.findall(r'class="([^"]*)"', f.read_text()):
            classes.update(re.sub(r"\{[{%].*?[%}]\}", " ", attr).split())
    h = hashlib.sha256(" ".join(sorted(classes)).encode())
    for f in OTHER:
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def main() -> None:
    src = ROOT / "app" / "static" / "vendor" / "_input.css"
    src.write_text("@tailwind base;@tailwind components;@tailwind utilities;\n")
    try:
        subprocess.run(
            [
                "npx",
                "--yes",
                TAILWIND,
                "-c",
                "tailwind.config.js",
                "-i",
                str(src),
                "-o",
                str(OUT),
                "--minify",
            ],
            cwd=ROOT,
            check=True,
        )
    finally:
        src.unlink()
    OUT.write_text(
        f"/* {TAILWIND} (MIT). Built by scripts/build_css.py. sources:{source_hash()} */\n"
        + OUT.read_text()
    )
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
