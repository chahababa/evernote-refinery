from bs4 import BeautifulSoup

from evernote_refinery.markdown import enml_to_markdown
from evernote_refinery.normalizer import normalize_enml


def test_normalize_enml_converts_evernote_todos_to_html_checkboxes():
    enml = """<?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">
    <en-note><div><en-todo checked="true"/>Done</div><div><en-todo/>Todo</div></en-note>
    """

    html = normalize_enml(enml)
    soup = BeautifulSoup(html, "html.parser")
    checkboxes = soup.find_all("input", {"type": "checkbox"})

    assert len(checkboxes) == 2
    assert checkboxes[0].get("checked") == "checked"
    assert checkboxes[0].get("disabled") == "disabled"
    assert checkboxes[1].get("checked") is None
    assert checkboxes[1].get("disabled") == "disabled"
    assert "Done" in html
    assert "Todo" in html
    assert "en-todo" not in html


def test_normalize_enml_rewrites_en_media_using_resource_hash_map():
    enml = '<en-note><div>附件 <en-media type="image/png" hash="abc123"/></div></en-note>'

    html = normalize_enml(enml, resource_paths={"abc123": "assets/image.png"})
    image = BeautifulSoup(html, "html.parser").find("img")

    assert image is not None
    assert image.get("src") == "assets/image.png"
    assert image.get("alt") == "attachment: abc123"
    assert "en-media" not in html


def test_normalize_enml_marks_missing_media_references_without_losing_hash():
    enml = '<en-note><div><en-media type="application/pdf" hash="missing"/></div></en-note>'

    html = normalize_enml(enml, resource_paths={})
    link = BeautifulSoup(html, "html.parser").find("a")

    assert link is not None
    assert link.get("href") == ""
    assert link.get("data-missing-resource") == "missing"
    assert link.text == "missing attachment: missing"
    assert "en-media" not in html


def test_normalize_enml_preserves_encrypted_blocks_as_redacted_notice():
    enml = '<en-note><div>before</div><en-crypt hint="private">secret</en-crypt><div>after</div></en-note>'

    html = normalize_enml(enml)
    encrypted = BeautifulSoup(html, "html.parser").find("span", {"data-evernote-encrypted": "true"})

    assert "before" in html
    assert "after" in html
    assert encrypted is not None
    assert encrypted.text == "[Encrypted content: private]"
    assert "secret" not in html
    assert "en-crypt" not in html


def test_enml_to_markdown_handles_multiple_todos_in_same_block_without_detached_tree_error():
    enml = """
    <en-note>
      <div><en-todo checked="true"/>第一項<br/><en-todo/>第二項</div>
    </en-note>
    """

    markdown = enml_to_markdown(enml)

    assert markdown == "- [x] 第一項\n- [ ] 第二項"
