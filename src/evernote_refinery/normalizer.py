from __future__ import annotations

from collections.abc import Mapping

from bs4 import BeautifulSoup

_IMAGE_MIME_PREFIX = "image/"


def normalize_enml(enml: str, resource_paths: Mapping[str, str] | None = None) -> str:
    """Normalize Evernote ENML into plain HTML before Markdown conversion.

    Evernote-specific tags such as ``en-todo``, ``en-media``, and ``en-crypt``
    are not understood by generic HTML-to-Markdown tools. This function rewrites
    them into conservative HTML equivalents while preserving useful references.
    """

    soup = BeautifulSoup(_strip_xml_preamble(enml), "html.parser")
    resource_paths = resource_paths or {}

    for todo in soup.find_all("en-todo"):
        checkbox = soup.new_tag("input", type="checkbox")
        checkbox["disabled"] = "disabled"
        if (todo.get("checked") or "").lower() == "true":
            checkbox["checked"] = "checked"
        todo.replace_with(checkbox)

    for media in soup.find_all("en-media"):
        body_hash = media.get("hash", "")
        mime = media.get("type", "")
        path = resource_paths.get(body_hash)
        if path and mime.startswith(_IMAGE_MIME_PREFIX):
            replacement = soup.new_tag("img", src=path)
            replacement["alt"] = f"attachment: {body_hash}"
        elif path:
            replacement = soup.new_tag("a", href=path)
            replacement.string = path
        else:
            replacement = soup.new_tag("a", href="")
            replacement["data-missing-resource"] = body_hash
            replacement.string = f"missing attachment: {body_hash}"
        media.replace_with(replacement)

    for encrypted in soup.find_all("en-crypt"):
        hint = encrypted.get("hint") or "no hint"
        replacement = soup.new_tag("span")
        replacement["data-evernote-encrypted"] = "true"
        replacement.string = f"[Encrypted content: {hint}]"
        encrypted.replace_with(replacement)

    root = soup.find("en-note")
    if root is not None:
        return "".join(str(child) for child in root.children).strip()
    return str(soup).strip()


def _strip_xml_preamble(enml: str) -> str:
    lines = []
    for line in enml.splitlines():
        stripped = line.strip()
        if stripped.startswith("<?xml") or stripped.startswith("<!DOCTYPE"):
            continue
        lines.append(line)
    return "\n".join(lines)
