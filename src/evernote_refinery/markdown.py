from __future__ import annotations

from collections.abc import Mapping

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

from evernote_refinery.normalizer import normalize_enml


def enml_to_markdown(
    enml: str,
    resource_paths: Mapping[str, str] | None = None,
    resource_mime_types: Mapping[str, str] | None = None,
) -> str:
    """Convert Evernote ENML to Markdown after normalizing custom tags."""

    html = normalize_enml(
        enml,
        resource_paths=resource_paths,
        resource_mime_types=resource_mime_types,
    )
    html = _rewrite_checkbox_divs_as_tasks(html)
    return html_to_markdown(html, heading_style="ATX").strip()


def _rewrite_checkbox_divs_as_tasks(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for checkbox in soup.find_all("input", {"type": "checkbox"}):
        parent = checkbox.parent
        checked = checkbox.has_attr("checked")
        marker = "[x]" if checked else "[ ]"
        text = parent.get_text(" ", strip=True) if parent else ""
        task_text = f"- {marker} {text}".strip()
        if parent is not None and parent.name in {"div", "p", "li"}:
            checkbox.extract()
            parent.clear()
            parent.string = task_text
        else:
            checkbox.replace_with(task_text)
    return str(soup)
