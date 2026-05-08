from evernote_refinery.markdown import enml_to_markdown


def test_enml_to_markdown_preserves_todo_state_as_task_list_items():
    enml = '<en-note><div><en-todo checked="true"/>Done</div><div><en-todo/>Todo</div></en-note>'

    markdown = enml_to_markdown(enml)

    assert "- [x] Done" in markdown
    assert "- [ ] Todo" in markdown
    assert "en-todo" not in markdown


def test_enml_to_markdown_converts_media_to_markdown_image():
    enml = '<en-note><div><en-media type="image/png" hash="abc123"/></div></en-note>'

    markdown = enml_to_markdown(enml, resource_paths={"abc123": "assets/image.png"})

    assert "![attachment: abc123](assets/image.png)" in markdown
    assert "en-media" not in markdown


def test_enml_to_markdown_redacts_encrypted_content():
    enml = '<en-note><en-crypt hint="private">secret</en-crypt></en-note>'

    markdown = enml_to_markdown(enml)

    assert "[Encrypted content: private]" in markdown
    assert "secret" not in markdown
