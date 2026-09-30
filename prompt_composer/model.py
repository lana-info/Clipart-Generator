"""Versioned, JSON-safe prompt snapshots. Validation never changes its argument."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from studio_asset_api import AssetHandle, AssetHandleError

FIELD_KEYS = (
    "subject", "appearance", "wardrobe", "material", "color", "location",
    "surface", "style", "lighting", "time", "camera", "shot", "angle",
    "action", "duration", "aspect", "exclusions",
)
MODES = ("image", "reels")
SUBJECT_TYPES = ("person", "character", "animal", "product", "object", "place")
_DRAFT_KEYS = {
    "schema_version", "catalog_version", "revision", "mode", "subject_type",
    "fields", "locks", "references", "profile_id", "base_en", "base_ru",
    "manual_en", "manual_ru", "translation_stale", "name", "selection_seed",
}


def new_draft() -> dict:
    return {
        "schema_version": 1, "catalog_version": 1, "revision": 1,
        "mode": "image", "subject_type": "object",
        "fields": {"subject": {"ru": "предмет", "en": "object"}}, "locks": [],
        "references": [], "profile_id": None, "base_en": "", "base_ru": "",
        "manual_en": None, "manual_ru": None, "translation_stale": False,
        "name": "Новый промпт", "selection_seed": 0,
    }


def _text(value: object, path: str, limit: int = 4000) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be text")
    if len(value) > limit:
        raise ValueError(f"{path} exceeds {limit} characters")
    if "\x00" in value:
        raise ValueError(f"{path} contains a null character")
    return value


def validate_draft(draft: dict) -> dict:
    if not isinstance(draft, dict):
        raise ValueError("Draft must be an object")
    missing = _DRAFT_KEYS - draft.keys()
    extra = draft.keys() - _DRAFT_KEYS
    if missing or extra:
        raise ValueError(f"Draft keys invalid: missing {sorted(missing)}, unknown {sorted(extra)}")
    if type(draft["schema_version"]) is not int or draft["schema_version"] != 1:
        raise ValueError("Unsupported prompt schema_version; this draft needs migration")
    if type(draft["catalog_version"]) is not int or draft["catalog_version"] < 1:
        raise ValueError("catalog_version must be a positive integer")
    if type(draft["revision"]) is not int or draft["revision"] < 1:
        raise ValueError("revision must be a positive integer")
    if draft["mode"] not in MODES:
        raise ValueError("mode must be image or reels")
    if draft["subject_type"] not in SUBJECT_TYPES:
        raise ValueError("Unknown subject_type")
    if not isinstance(draft["fields"], dict):
        raise ValueError("fields must be an object")
    if len(draft["fields"]) > len(FIELD_KEYS):
        raise ValueError("Too many fields")
    for key, pair in draft["fields"].items():
        if key not in FIELD_KEYS or not isinstance(pair, dict) or set(pair) != {"ru", "en"}:
            raise ValueError(f"Invalid bilingual field: {key}")
        _text(pair["ru"], f"fields.{key}.ru", 600)
        _text(pair["en"], f"fields.{key}.en", 600)
    locks = draft["locks"]
    if not isinstance(locks, list) or len(locks) != len(set(map(str, locks))):
        raise ValueError("locks must be a list of unique fields")
    if any(not isinstance(key, str) or key not in FIELD_KEYS for key in locks):
        raise ValueError("locks contains an unknown field")
    refs = draft["references"]
    if not isinstance(refs, list) or len(refs) > 5 or any(not isinstance(ref, dict) for ref in refs):
        raise ValueError("references must contain at most five asset handles")
    for ref in refs:
        try:
            AssetHandle.from_dict(ref)
        except AssetHandleError as exc:
            raise ValueError(f"reference must be a valid Studio AssetHandle: {exc}") from exc
    if draft["profile_id"] is not None:
        _text(draft["profile_id"], "profile_id", 200)
    for key in ("base_en", "base_ru", "name"):
        _text(draft[key], key, 12000 if key.startswith("base_") else 200)
    for key in ("manual_en", "manual_ru"):
        if draft[key] is not None:
            _text(draft[key], key, 12000)
    if type(draft["translation_stale"]) is not bool:
        raise ValueError("translation_stale must be boolean")
    if type(draft["selection_seed"]) is not int or not 0 <= draft["selection_seed"] <= 2**63 - 1:
        raise ValueError("selection_seed must be a nonnegative integer")
    return deepcopy(draft)


def draft_fingerprint(draft: dict) -> str:
    snapshot = validate_draft(draft)
    return sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def rendered_text(draft: dict, language: str = "en") -> str:
    snapshot = validate_draft(draft)
    if language not in ("en", "ru"):
        raise ValueError("language must be en or ru")
    return snapshot[f"manual_{language}"] if snapshot[f"manual_{language}"] is not None else snapshot[f"base_{language}"]
