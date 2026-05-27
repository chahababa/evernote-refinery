from __future__ import annotations

from collections.abc import Mapping

from bs4 import BeautifulSoup, NavigableString
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

    for parent in list(soup.find_all(["div", "p", "li"])):
        checkboxes = parent.find_all("input", {"type": "checkbox"}, recursive=False)
        if not checkboxes:
            continue

        if len(checkboxes) == 1:
            checkbox = checkboxes[0]
            checked = checkbox.has_attr("checked")
            marker = "[x]" if checked else "[ ]"
            text = parent.get_text(" ", strip=True)
            task_text = f"- {marker} {text}".strip()
            checkbox.extract()
            parent.clear()
            parent.string = task_text
            continue

        task_lines = _task_lines_from_checkbox_block(parent)
        parent.clear()
        parent.string = "\n".join(task_lines)

    for checkbox in list(soup.find_all("input", {"type": "checkbox"})):
        if checkbox.parent is None:
            continue
        checked = checkbox.has_attr("checked")
        marker = "[x]" if checked else "[ ]"
        checkbox.replace_with(NavigableString(f"- {marker} "))
    return str(soup)


def _task_lines_from_checkbox_block(parent) -> list[str]:
    task_lines: list[str] = []
    marker: str | None = None
    text_parts: list[str] = []

    def flush() -> None:
        nonlocal marker, text_parts
        if marker is None:
            return
        text = " ".join(part for part in text_parts if part).strip()
        task_lines.append(f"- {marker} {text}".strip())
        text_parts = []

    for child in list(parent.children):
        if getattr(child, "name", None) == "input" and child.get("type") == "checkbox":
            flush()
            marker = "[x]" if child.has_attr("checked") else "[ ]"
            text_parts = []
            continue
        if getattr(child, "name", None) == "br":
            continue
        text = child.get_text(" ", strip=True) if hasattr(child, "get_text") else str(child).strip()
        if text:
            text_parts.append(text)

    flush()
    return task_lines
