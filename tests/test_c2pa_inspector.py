import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from metadata_inspector import inspect_c2pa_presence, inspect_image_metadata


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
C2PA_UUID = bytes.fromhex("6332706100110010800000aa00389b71")
SECRET_MANIFEST_TEXT = b"manifest-value-must-not-leak"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def png_chunk(chunk_type, payload):
    body = chunk_type + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def png_ihdr():
    return png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))


def add_png_chunk_after_ihdr(path, chunk_type, payload):
    data = Path(path).read_bytes()
    ihdr_length = struct.unpack_from(">I", data, len(PNG_SIGNATURE))[0]
    insertion = len(PNG_SIGNATURE) + 12 + ihdr_length
    Path(path).write_bytes(data[:insertion] + png_chunk(chunk_type, payload) + data[insertion:])


def jumbf_box(box_type, payload):
    return struct.pack(">I4s", len(payload) + 8, box_type) + payload


def c2pa_jumbf(uuid=C2PA_UUID, label=b"c2pa\x00", extended_outer=False):
    description = jumbf_box(b"jumd", uuid + b"\x03" + label)
    content = jumbf_box(b"json", SECRET_MANIFEST_TEXT * 4)
    payload = description + content
    if extended_outer:
        return struct.pack(">I4sQ", 1, b"jumb", len(payload) + 16) + payload
    return jumbf_box(b"jumb", payload)


def jpeg_app11_segments(jumbf, split_at=None, instance=b"\x02\x11"):
    if split_at is None:
        parts = [jumbf]
    else:
        split_points = [split_at] if isinstance(split_at, int) else list(split_at)
        boundaries = [0, *split_points, len(jumbf)]
        parts = [jumbf[start:end] for start, end in zip(boundaries, boundaries[1:])]
    segments = []
    payload_sizes = []
    for index, part in enumerate(parts, start=1):
        repeated_box_header = b"" if index == 1 else jumbf[:8]
        payload = b"JP" + instance + struct.pack(">I", index) + repeated_box_header + part
        segments.append(b"\xff\xeb" + struct.pack(">H", len(payload) + 2) + payload)
        payload_sizes.append(len(payload))
    return b"".join(segments), payload_sizes


def add_jpeg_segments(path, segments):
    data = Path(path).read_bytes()
    Path(path).write_bytes(data[:2] + segments + data[2:])


class C2paInspectorTests(unittest.TestCase):
    def test_png_cabx_is_reported_separately_and_read_only(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-png-") as temp_dir:
            path = Path(temp_dir) / "fixture.png"
            Image.new("RGBA", (8, 6), (20, 40, 60, 180)).save(path)
            payload = c2pa_jumbf() + b"https://example.invalid/remote-manifest"
            add_png_chunk_after_ihdr(path, b"caBX", payload)
            before_hash = file_hash(path)
            before_stat = path.stat()

            with patch("socket.create_connection", side_effect=AssertionError("network access is forbidden")):
                direct = inspect_c2pa_presence(path)
                integrated = inspect_image_metadata(path)

            self.assertEqual(direct["presence"], "present")
            self.assertEqual(direct["validation"], "not_validated")
            self.assertEqual(direct["scan_status"], "ok")
            self.assertEqual(direct["item_count"], 1)
            self.assertEqual(direct["segment_count"], 1)
            self.assertEqual(direct["size_bytes"], len(payload))
            self.assertEqual(direct["containers"], ["png_cabx"])
            self.assertEqual(integrated["status"], "ok")
            self.assertEqual(integrated["c2pa"], direct)
            self.assertNotIn(SECRET_MANIFEST_TEXT.decode(), json.dumps(integrated, sort_keys=True))
            self.assertEqual(file_hash(path), before_hash)
            self.assertEqual(path.stat().st_size, before_stat.st_size)
            self.assertEqual(path.stat().st_mtime_ns, before_stat.st_mtime_ns)

    def test_jpeg_c2pa_jumbf_and_continuation_are_detected(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-jpeg-") as temp_dir:
            path = Path(temp_dir) / "fixture.jpg"
            Image.new("RGB", (9, 7), (220, 180, 140)).save(path, format="JPEG")
            jumbf = c2pa_jumbf()
            segments, _ = jpeg_app11_segments(jumbf, split_at=56)
            add_jpeg_segments(path, segments)
            before_hash = file_hash(path)

            result = inspect_image_metadata(path)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["format"], "JPEG")
            self.assertEqual(result["c2pa"]["presence"], "present")
            self.assertEqual(result["c2pa"]["validation"], "not_validated")
            self.assertEqual(result["c2pa"]["scan_status"], "ok")
            self.assertEqual(result["c2pa"]["item_count"], 1)
            self.assertEqual(result["c2pa"]["segment_count"], 2)
            self.assertEqual(result["c2pa"]["size_bytes"], len(jumbf))
            self.assertEqual(result["c2pa"]["containers"], ["jpeg_app11_jumbf"])
            self.assertNotIn(SECRET_MANIFEST_TEXT.decode(), json.dumps(result, sort_keys=True))
            self.assertEqual(file_hash(path), before_hash)

    def test_jpeg_extended_lbox_fragmentation_is_counted_exactly(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-jpeg-xlbox-") as temp_dir:
            path = Path(temp_dir) / "extended-lbox.jpg"
            jumbf = c2pa_jumbf(extended_outer=True)
            segments, _ = jpeg_app11_segments(jumbf, split_at=(64, 110))
            path.write_bytes(b"\xff\xd8" + segments + b"\xff\xd9")

            result = inspect_c2pa_presence(path)

            self.assertEqual(result["presence"], "present")
            self.assertEqual(result["validation"], "not_validated")
            self.assertEqual(result["scan_status"], "ok")
            self.assertEqual(result["segment_count"], 3)
            self.assertEqual(result["size_bytes"], len(jumbf))

    def test_clean_and_non_c2pa_app11_files_report_not_present(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-clean-") as temp_dir:
            temp_path = Path(temp_dir)
            png_path = temp_path / "clean.png"
            jpeg_path = temp_path / "generic-app11.jpg"
            Image.new("RGB", (5, 4), "white").save(png_path)
            Image.new("RGB", (5, 4), "white").save(jpeg_path, format="JPEG")
            generic, _ = jpeg_app11_segments(c2pa_jumbf(uuid=b"\x00" * 16))
            add_jpeg_segments(jpeg_path, generic)

            clean_png = inspect_c2pa_presence(png_path)
            generic_jpeg = inspect_c2pa_presence(jpeg_path)

            for result in (clean_png, generic_jpeg):
                self.assertEqual(result["presence"], "not_present")
                self.assertEqual(result["validation"], "not_validated")
                self.assertEqual(result["scan_status"], "ok")
                self.assertEqual(result["item_count"], 0)
                self.assertEqual(result["containers"], [])

    def test_malformed_truncated_and_oversized_inputs_fail_safely(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-bounds-") as temp_dir:
            temp_path = Path(temp_dir)
            truncated_png = temp_path / "truncated.png"
            oversized_png = temp_path / "oversized.png"
            invalid_jpeg = temp_path / "invalid-length.jpg"
            truncated_jpeg = temp_path / "truncated-segment.jpg"

            truncated_png.write_bytes(
                PNG_SIGNATURE + png_ihdr() + struct.pack(">I4s", 100, b"caBX") + b"short"
            )
            oversized_png.write_bytes(
                PNG_SIGNATURE + png_ihdr() + struct.pack(">I4s", 0x80000000, b"caBX")
            )
            invalid_jpeg.write_bytes(b"\xff\xd8\xff\xeb\x00\x01")
            truncated_jpeg.write_bytes(b"\xff\xd8\xff\xeb\xff\xffJP")

            results = [
                inspect_c2pa_presence(truncated_png),
                inspect_c2pa_presence(oversized_png),
                inspect_c2pa_presence(invalid_jpeg),
                inspect_c2pa_presence(truncated_jpeg),
            ]

            self.assertEqual(results[0]["reason"], "truncated_png_chunk")
            self.assertEqual(results[1]["reason"], "png_chunk_length_exceeds_spec")
            self.assertEqual(results[2]["reason"], "invalid_jpeg_segment_length")
            self.assertEqual(results[3]["reason"], "truncated_jpeg_segment")
            for result in results:
                self.assertEqual(result["presence"], "unknown")
                self.assertEqual(result["validation"], "not_validated")
                self.assertIn(result["scan_status"], {"malformed", "limit_exceeded"})
                self.assertEqual(result["size_bytes"], 0)

    def test_jpeg_c2pa_segment_limit_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-segment-limit-") as temp_dir:
            path = Path(temp_dir) / "many-segments.jpg"
            jumbf = c2pa_jumbf()
            segments, _ = jpeg_app11_segments(jumbf, split_at=(56, 100))
            path.write_bytes(b"\xff\xd8" + segments + b"\xff\xd9")

            with patch("metadata_inspector._MAX_C2PA_SEGMENTS", 2):
                result = inspect_c2pa_presence(path)

            self.assertEqual(result["presence"], "present")
            self.assertEqual(result["validation"], "not_validated")
            self.assertEqual(result["scan_status"], "limit_exceeded")
            self.assertEqual(result["reason"], "c2pa_jpeg_data_exceeds_scan_limit")
            self.assertEqual(result["segment_count"], 3)

    def test_jpeg_declared_length_and_description_toggles_are_enforced(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-jumbf-validation-") as temp_dir:
            temp_path = Path(temp_dir)
            truncated_path = temp_path / "truncated-jumbf.jpg"
            toggles_path = temp_path / "invalid-toggles.jpg"
            unbounded_description_path = temp_path / "unbounded-description.jpg"
            oversized_description_path = temp_path / "oversized-description.jpg"

            truncated = bytearray(c2pa_jumbf())
            struct.pack_into(">I", truncated, 0, 4096)
            truncated_segments, _ = jpeg_app11_segments(bytes(truncated))
            truncated_path.write_bytes(b"\xff\xd8" + truncated_segments + b"\xff\xd9")

            invalid_toggles = bytearray(c2pa_jumbf())
            invalid_toggles[32] = 0
            toggle_segments, _ = jpeg_app11_segments(bytes(invalid_toggles))
            toggles_path.write_bytes(b"\xff\xd8" + toggle_segments + b"\xff\xd9")

            unbounded_description = bytearray(c2pa_jumbf())
            struct.pack_into(">I", unbounded_description, 8, 0)
            unbounded_segments, _ = jpeg_app11_segments(bytes(unbounded_description))
            unbounded_description_path.write_bytes(b"\xff\xd8" + unbounded_segments + b"\xff\xd9")

            oversized_description = bytearray(c2pa_jumbf())
            struct.pack_into(">I", oversized_description, 8, len(oversized_description) + 1)
            oversized_segments, _ = jpeg_app11_segments(bytes(oversized_description))
            oversized_description_path.write_bytes(b"\xff\xd8" + oversized_segments + b"\xff\xd9")

            truncated_result = inspect_c2pa_presence(truncated_path)
            toggles_result = inspect_c2pa_presence(toggles_path)
            unbounded_result = inspect_c2pa_presence(unbounded_description_path)
            oversized_result = inspect_c2pa_presence(oversized_description_path)

            self.assertEqual(truncated_result["presence"], "present")
            self.assertEqual(truncated_result["scan_status"], "malformed")
            self.assertEqual(truncated_result["reason"], "truncated_c2pa_jumbf")
            self.assertEqual(toggles_result["presence"], "present")
            self.assertEqual(toggles_result["scan_status"], "malformed")
            self.assertEqual(toggles_result["reason"], "invalid_jumbf_toggles")
            self.assertEqual(unbounded_result["presence"], "present")
            self.assertEqual(unbounded_result["scan_status"], "malformed")
            self.assertEqual(unbounded_result["reason"], "unbounded_c2pa_description_box")
            self.assertEqual(oversized_result["presence"], "present")
            self.assertEqual(oversized_result["scan_status"], "malformed")
            self.assertEqual(oversized_result["reason"], "c2pa_description_exceeds_outer_box")
            for result in (truncated_result, toggles_result, unbounded_result, oversized_result):
                self.assertEqual(result["validation"], "not_validated")

    def test_jpeg_sequence_gaps_and_extra_continuations_are_malformed(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-jumbf-sequence-") as temp_dir:
            temp_path = Path(temp_dir)
            gap_path = temp_path / "sequence-gap.jpg"
            extra_path = temp_path / "extra-continuation.jpg"
            jumbf = c2pa_jumbf()
            instance = b"\x02\x11"

            first_part = jumbf[:56]
            second_part = jumbf[56:]
            first_payload = b"JP" + instance + struct.pack(">I", 1) + first_part
            gap_payload = b"JP" + instance + struct.pack(">I", 3) + jumbf[:8] + second_part
            gap_segments = (
                b"\xff\xeb" + struct.pack(">H", len(first_payload) + 2) + first_payload
                + b"\xff\xeb" + struct.pack(">H", len(gap_payload) + 2) + gap_payload
            )
            gap_path.write_bytes(b"\xff\xd8" + gap_segments + b"\xff\xd9")

            complete, _ = jpeg_app11_segments(jumbf)
            extra_payload = b"JP" + instance + struct.pack(">I", 2) + jumbf[:8] + b"x"
            extra_segment = b"\xff\xeb" + struct.pack(">H", len(extra_payload) + 2) + extra_payload
            extra_path.write_bytes(b"\xff\xd8" + complete + extra_segment + b"\xff\xd9")

            gap_result = inspect_c2pa_presence(gap_path)
            extra_result = inspect_c2pa_presence(extra_path)

            self.assertEqual(gap_result["presence"], "present")
            self.assertEqual(gap_result["scan_status"], "malformed")
            self.assertEqual(gap_result["reason"], "invalid_c2pa_jumbf_sequence")
            self.assertEqual(extra_result["presence"], "present")
            self.assertEqual(extra_result["scan_status"], "malformed")
            self.assertEqual(extra_result["reason"], "unexpected_c2pa_jumbf_continuation")


if __name__ == "__main__":
    unittest.main()
