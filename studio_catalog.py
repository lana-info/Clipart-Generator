"""Pure, bounded presentation contract for Studio's module catalogue.

The availability values are display hints, not an authorization decision.  A
caller must recheck its current trusted entitlement and runtime gate immediately
before executing every ``open``, ``update``, ``download``, or ``purchase``
action returned here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_MODULE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_MAX_TEXT_LENGTH = 500


def _module_id(value: str) -> None:
    if not isinstance(value, str) or not _MODULE_ID.fullmatch(value):
        raise ValueError("Invalid module identifier")


def _content(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > _MAX_TEXT_LENGTH:
        raise ValueError(f"Invalid catalogue {field}")


def _flag(value: bool, field: str) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field} must be a boolean")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    module_id: str
    title: str
    description: str
    artwork_key: str
    released: bool = False

    def __post_init__(self) -> None:
        _module_id(self.module_id)
        _content(self.title, "title")
        _content(self.description, "description")
        _content(self.artwork_key, "artwork key")
        _flag(self.released, "released")


@dataclass(frozen=True, slots=True)
class ModuleAvailability:
    """Non-authoritative catalogue hints; unknown rights must be represented as false."""

    installed: bool = False
    entitled: bool = False
    compatible: bool = True
    update_available: bool = False
    open_supported: bool = False
    download_supported: bool = False
    purchase_supported: bool = False
    entitlement_known: bool = True
    release_known: bool = False
    release_available: bool = False

    def __post_init__(self) -> None:
        for name in (
            "installed", "entitled", "compatible", "update_available",
            "open_supported", "download_supported", "purchase_supported", "entitlement_known",
            "release_known", "release_available",
        ):
            _flag(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class CardAction:
    """An immutable primary-card instruction, never an authorization grant."""

    action: str
    label: str
    enabled: bool
    reason: str


def card_action(entry: CatalogEntry, availability: ModuleAvailability) -> CardAction:
    """Choose one primary card action without performing I/O or authorization.

    The returned action is only suitable for presentation.  The host must
    recheck the current trusted entitlement and operation-specific runtime gate
    when the user activates any executable action.
    """
    if not isinstance(entry, CatalogEntry) or not isinstance(availability, ModuleAvailability):
        raise TypeError("entry and availability must use the catalogue contract")

    if not entry.released:
        return CardAction("soon", "Скоро выйдет", False, "Модуль ещё не выпущен.")
    if not availability.compatible:
        return CardAction("unavailable", "Недоступно", False, "Модуль несовместим с этой версией Studio.")
    if not availability.entitlement_known:
        return CardAction("verify", "Проверить доступ", True, "Требуется проверка лицензии.")

    if availability.entitled and availability.installed:
        if availability.update_available and availability.download_supported:
            return CardAction("update", "Обновить", True, "")
        if availability.open_supported:
            return CardAction("open", "Открыть", True, "Доступно обновление модуля." if availability.update_available else "")
        return CardAction("open", "Открыть", False, "Открытие модуля сейчас недоступно.")

    if availability.entitled:
        if availability.release_known and not availability.release_available:
            return CardAction("pending", "Ожидается выпуск", False, "Доступ есть; совместимый пакет ещё не опубликован.")
        return CardAction(
            "download", "Скачать", availability.download_supported,
            "" if availability.download_supported else "Скачивание модуля сейчас недоступно.",
        )

    # This deliberately includes copied or previously installed packages after
    # a right is revoked: installation alone never permits opening a module.
    return CardAction(
        "denied", "Нет доступа", False,
        "Модуль не входит в вашу лицензию.",
    )
