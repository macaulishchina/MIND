"""Helpers for reading the split static frontend asset surface."""

from __future__ import annotations

import re
from pathlib import Path

_STYLESHEET_HREF_PATTERN = re.compile(r'<link\s+rel="stylesheet"\s+href="([^"]+)"')


def load_frontend_javascript(root: str | Path) -> str:
    frontend_root = Path(root)
    js_sources = [(frontend_root / "app.js").read_text(encoding="utf-8")]
    app_module_root = frontend_root / "app"
    if app_module_root.is_dir():
        js_sources.extend(
            path.read_text(encoding="utf-8") for path in sorted(app_module_root.rglob("*.js"))
        )
    return "\n".join(js_sources)


def linked_stylesheet_paths(root: str | Path, index_html: str) -> tuple[Path, ...]:
    frontend_root = Path(root)
    matches = _STYLESHEET_HREF_PATTERN.findall(index_html)
    paths: list[Path] = []
    for href in matches:
        normalized = href.removeprefix("./")
        path = frontend_root / normalized
        if path.is_file():
            paths.append(path)
    if not paths and (frontend_root / "styles.css").is_file():
        paths.append(frontend_root / "styles.css")
    return tuple(paths)


def load_frontend_stylesheets(root: str | Path, index_html: str) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in linked_stylesheet_paths(root, index_html)
    )
