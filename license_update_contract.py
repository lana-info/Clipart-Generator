"""Pure lifecycle policy for license validation and signed updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class LicenseLifecycleState(StrEnum):
    VALID = "valid"
    REVOKED = "revoked"
    EXPIRED = "expired"
    OUTAGE = "outage"
    TAMPERED = "tampered"


@dataclass(frozen=True)
class LicenseUpdatePolicy:
    endpoint_version: str = "v1"
    timeout_seconds: int = 30
    # Скачивание артефакта (сотни МБ) — щедрее API-запросов (владелец 2026-10-31:
    # 243 МБ при 20 с на чанк 1 МБ рвались на медленном канале).
    download_timeout_seconds: int = 120
    download_chunk_bytes: int = 256 * 1024
    download_attempts: int = 2
    clock_skew_seconds: int = 300
    accepted_key_ids: tuple[str, ...] = ("license-v1",)
    outage_allows_cached_access: bool = False

    def accepts_key(self, key_id: str) -> bool:
        return str(key_id or "") in self.accepted_key_ids

    def validate_timestamp(self, value: datetime, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        timestamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return abs((current - timestamp).total_seconds()) <= self.clock_skew_seconds


def classify_failure(*, revoked: bool = False, expired: bool = False, tampered: bool = False, outage: bool = False) -> LicenseLifecycleState:
    if tampered:
        return LicenseLifecycleState.TAMPERED
    if revoked:
        return LicenseLifecycleState.REVOKED
    if expired:
        return LicenseLifecycleState.EXPIRED
    if outage:
        return LicenseLifecycleState.OUTAGE
    return LicenseLifecycleState.VALID
