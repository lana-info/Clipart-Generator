"""Small, provider-independent locale contract for the v3 UI.

The application locale is intentionally separate from prompt language, model
identifiers and internal status values. Full UI translation can build on this
contract without changing persisted project data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


DEFAULT_LOCALE = "ru"
SUPPORTED_LOCALES = ("ru", "en")


def normalize_locale(value: Any, *, default: str = DEFAULT_LOCALE) -> str:
    """Return a supported base language for a user or OS language tag."""

    fallback = str(default or DEFAULT_LOCALE).strip().casefold().split("-", 1)[0]
    if fallback not in SUPPORTED_LOCALES:
        fallback = DEFAULT_LOCALE
    raw = str(value or "").strip().replace("_", "-").casefold()
    base = raw.split("-", 1)[0]
    return base if base in SUPPORTED_LOCALES else fallback


def app_locale_from_settings(settings: Mapping[str, Any] | None) -> str:
    """Read only the UI locale setting, preserving prompt-language semantics."""

    source = settings if isinstance(settings, Mapping) else {}
    return normalize_locale(source.get("app_language"))


def with_app_locale(
    settings: Mapping[str, Any] | None,
    locale: Any,
) -> dict[str, Any]:
    """Return settings with a normalized UI locale, without mutating input."""

    result = dict(settings) if isinstance(settings, Mapping) else {}
    result["app_language"] = normalize_locale(locale)
    return result


__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "app_locale_from_settings",
    "normalize_locale",
    "with_app_locale",
]
