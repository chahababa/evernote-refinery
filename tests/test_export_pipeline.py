from evernote_refinery.export import build_exports_from_enex


def test_build_exports_from_enex_streams_notes_and_exports_markdown(tmp_path):
    results = list(build_exports_from_enex("tests/fixtures/simple.enex", tmp_path))

    assert len(results) == 1
    result = results[0]
    assert result.title == "早餐店 SOP"
    assert result.metadata["tags"] == ["工作", "巡店"]
    assert result.features["resource_count"] == 1
    assert result.features["has_attachments"] is True
    assert "檢查瓦斯" in result.markdown
    assert result.attachments.paths_by_hash
    for relative_path in result.attachments.paths_by_hash.values():
        assert (tmp_path / relative_path).exists()
