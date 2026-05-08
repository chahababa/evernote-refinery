from evernote_refinery.attachments import write_attachments
from evernote_refinery.markdown import enml_to_markdown
from evernote_refinery.parser import Resource


def test_written_attachment_maps_can_drive_markdown_media_conversion(tmp_path):
    resources = [
        Resource(
            mime="image/png",
            file_name="photo.png",
            data=b"fake png bytes",
            body_hash="abc123",
        )
    ]
    enml = '<en-note><div><en-media hash="abc123"/></div></en-note>'

    attachments = write_attachments(resources, tmp_path)
    markdown = enml_to_markdown(
        enml,
        resource_paths=attachments.paths_by_hash,
        resource_mime_types=attachments.mime_types_by_hash,
    )

    assert "![attachment: abc123](assets/abc123-photo.png)" in markdown
