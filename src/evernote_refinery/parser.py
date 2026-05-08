from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from lxml import etree


@dataclass(frozen=True)
class Resource:
    mime: str | None
    file_name: str | None
    data: bytes
    body_hash: str


@dataclass(frozen=True)
class Note:
    title: str
    created: str | None
    updated: str | None
    tags: list[str] = field(default_factory=list)
    content: str = ""
    resources: list[Resource] = field(default_factory=list)


def parse_enex(path: str | Path) -> Iterator[Note]:
    """Stream notes from an Evernote ENEX export.

    The parser yields one note at a time and clears processed XML nodes so large
    exports do not keep the full tree in memory.
    """

    for _event, elem in etree.iterparse(
        str(path),
        events=("end",),
        tag="note",
        load_dtd=False,
        resolve_entities=False,
        no_network=True,
        recover=True,
        huge_tree=True,
    ):
        yield _parse_note(elem)
        _clear_element(elem)


def _parse_note(elem: etree._Element) -> Note:
    return Note(
        title=_text(elem, "title") or "Untitled",
        created=_text(elem, "created"),
        updated=_text(elem, "updated"),
        tags=[tag.text or "" for tag in elem.findall("tag")],
        content=_text(elem, "content") or "",
        resources=[_parse_resource(resource) for resource in elem.findall("resource")],
    )


def _parse_resource(elem: etree._Element) -> Resource:
    raw_data = _text(elem, "data") or ""
    data = base64.b64decode("".join(raw_data.split())) if raw_data.strip() else b""
    return Resource(
        mime=_text(elem, "mime"),
        file_name=_text(elem, "resource-attributes/file-name"),
        data=data,
        body_hash=hashlib.sha256(data).hexdigest(),
    )


def _text(elem: etree._Element, path: str) -> str | None:
    found = elem.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def _clear_element(elem: etree._Element) -> None:
    elem.clear()
    parent = elem.getparent()
    if parent is None:
        return
    while elem.getprevious() is not None:
        del parent[0]
