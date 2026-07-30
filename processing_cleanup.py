"""Shared metadata-cleanup field contract for all processing modes."""

METADATA_CLEANUP_FIELDS = (
    "remove_exif",
    "remove_xmp",
    "remove_iptc",
    "remove_comments_text",
    "remove_embedded_thumbnail",
    "remove_generator_fields",
    "remove_embedded_c2pa",
)
