"""Shared SEO metadata and discovery-file helpers for the combined site."""

from __future__ import annotations

import html
import json
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


SITE_ORIGIN = "https://cuhk-minor.coffeebreak.work"
SITE_NAME = "CUHK Programme Information"


def absolute_url(path: str) -> str:
    """Return an absolute canonical URL on the one public production origin."""
    normalized = "/" + path.lstrip("/")
    return SITE_ORIGIN + normalized


def seo_head(
    title: str,
    description: str,
    canonical_path: str,
    structured_data: dict | list | None = None,
) -> str:
    """Build non-visible search and sharing metadata for an HTML page."""
    canonical = absolute_url(canonical_path)
    title_attr = html.escape(title, quote=True)
    description_attr = html.escape(description, quote=True)
    canonical_attr = html.escape(canonical, quote=True)
    blocks = [
        f"<title>{title_attr}</title>",
        f'<meta name="description" content="{description_attr}">',
        '<meta name="robots" content="index,follow">',
        f'<link rel="canonical" href="{canonical_attr}">',
        f'<meta property="og:title" content="{title_attr}">',
        f'<meta property="og:description" content="{description_attr}">',
        f'<meta property="og:url" content="{canonical_attr}">',
        f'<meta property="og:site_name" content="{html.escape(SITE_NAME, quote=True)}">',
        '<meta property="og:type" content="website">',
        '<meta name="twitter:card" content="summary">',
    ]
    if structured_data:
        payload = json.dumps(structured_data, ensure_ascii=False, separators=(",", ":"))
        blocks.append(f'<script type="application/ld+json">{payload.replace("</", "<\\/")}</script>')
    return "\n".join(blocks)


def breadcrumb_data(items: list[tuple[str, str | None]]) -> dict:
    """Build schema.org BreadcrumbList data from (label, path) pairs."""
    elements = []
    for position, (name, path) in enumerate(items, start=1):
        item = {
            "@type": "ListItem",
            "position": position,
            "name": name,
        }
        if path is not None:
            item["item"] = absolute_url(path)
        elements.append(item)
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": elements,
    }


def _published_path(path: Path, site_root: Path) -> str:
    relative = path.relative_to(site_root).as_posix()
    if relative.endswith("/index.html"):
        return "/" + relative[: -len("index.html")]
    if relative.endswith(".html"):
        return "/" + relative[: -len(".html")]
    return "/" + relative


def _year_directories(parent: Path) -> list[str]:
    if not parent.exists():
        return []
    return sorted(
        directory.name
        for directory in parent.iterdir()
        if directory.is_dir()
        and "_" in directory.name
        and (directory / "index.html").exists()
    )


def write_discovery_files(site_root: Path) -> None:
    """Generate sitemap.xml, robots.txt, and Cloudflare Pages redirects."""
    minor_years = _year_directories(site_root)
    major_years = _year_directories(site_root / "major")
    if not minor_years:
        return

    page_files: list[Path] = []
    for year in minor_years:
        year_dir = site_root / year
        page_files.extend(path for path in (year_dir / "index.html", year_dir / "checker.html") if path.exists())
        page_files.extend(sorted((year_dir / "minors").glob("*.html")))
    for year in major_years:
        year_dir = site_root / "major" / year
        page_files.append(year_dir / "index.html")
        page_files.extend(sorted((year_dir / "majors").glob("*.html")))

    urls = sorted({absolute_url(_published_path(path, site_root)) for path in page_files})
    sitemap = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    sitemap.extend(f"  <url><loc>{xml_escape(url)}</loc></url>" for url in urls)
    sitemap.append("</urlset>")
    (site_root / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")

    (site_root / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        f"Sitemap: {absolute_url('/sitemap.xml')}\n",
        encoding="utf-8",
    )

    latest_minor = minor_years[-1]
    redirects = [f"/ /{latest_minor}/ 301"]
    if major_years:
        redirects.append(f"/major /major/{major_years[-1]}/ 301")
        redirects.append(f"/major/ /major/{major_years[-1]}/ 301")
    redirects.append(
        "/2025_26/minors/HB_Minor_Programme_in_Hong_Kong_Sign_Language "
        "/2025_26/minors/Hong_Kong_Sign_Language 301"
    )
    (site_root / "_redirects").write_text("\n".join(redirects) + "\n", encoding="utf-8")
