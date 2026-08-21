"""Signed, licensed Windows update client for the V3 application."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib import error, request
from urllib.parse import urlparse

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from license_client import LicenseClient, LicenseError, NoRedirectHandler
from license_update_contract import LicenseUpdatePolicy


MAX_UPDATE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_UPDATE_INSTALLER_BYTES = 512 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_PLATFORM_ARTIFACT = {
    "windows-x64": (".exe", "application/vnd.microsoft.portable-executable"),
    "macos-arm64": (".zip", "application/zip"),
    "macos-x64": (".zip", "application/zip"),
}


class UpdateError(RuntimeError):
    """Bounded user-safe update failure."""


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    filename: str
    size: int
    sha256: str
    download_url: str
    notes: str = ""
    correlation_id: str = ""


def current_platform_id() -> str:
    """Return the update platform used by the current packaged application."""
    if sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "macos-arm64"
    if sys.platform == "darwin":
        return "macos-x64"
    return "windows-x64"


def _decode_public_key(value: str) -> Ed25519PublicKey:
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise UpdateError("Некорректный ключ подписи обновлений") from exc
    if len(raw) != 32:
        raise UpdateError("Некорректный ключ подписи обновлений")
    return Ed25519PublicKey.from_public_bytes(raw)


def _decode_signature(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 256:
        raise UpdateError("Повреждена подпись обновления")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise UpdateError("Повреждена подпись обновления") from exc
    if len(raw) != 64:
        raise UpdateError("Повреждена подпись обновления")
    return raw


def _version(value: object) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        raise UpdateError("Сервер вернул некорректную версию обновления")
    parts = [int(item) for item in value.split(".")]
    parts.extend([0] * (3 - len(parts)))
    if any(item > 999_999 for item in parts):
        raise UpdateError("Сервер вернул некорректную версию обновления")
    return tuple(parts)


class UpdateClient:
    def __init__(
        self,
        license_client: LicenseClient,
        public_keys: Mapping[str, str] | None = None,
        *,
        current_version: str,
        download_directory: str | Path,
        platform_id: str = "windows-x64",
        timeout: int = 20,
    ) -> None:
        self.license_client = license_client
        self.lifecycle_policy = LicenseUpdatePolicy()
        self.current_version = current_version
        if platform_id not in _PLATFORM_ARTIFACT:
            raise UpdateError("Эта платформа обновлений не поддерживается")
        self.platform_id = platform_id
        self.download_directory = Path(download_directory)
        self.timeout = max(1, min(int(timeout), self.lifecycle_policy.timeout_seconds))
        self._public_keys = {
            name: _decode_public_key(value) for name, value in (public_keys or {}).items()
        }
        _version(current_version)

    def check(self) -> UpdateRelease | None:
        self._ensure_update_key()
        try:
            envelope, device_key, nonce = self.license_client.authenticated_request(
                "/api/v1/releases/manifest",
                {"platform": self.platform_id},
            )
        except LicenseError as exc:
            raise UpdateError("Не удалось проверить обновления на сервере") from exc
        payload = self._verify_manifest(envelope)
        if payload.get("product_id") != self.license_client.product_id:
            raise UpdateError("Манифест предназначен другому продукту")
        if payload.get("platform") != self.platform_id:
            raise UpdateError("Манифест предназначен другой платформе")
        if payload.get("device_key") != device_key or payload.get("nonce") != nonce:
            raise UpdateError("Манифест не соответствует текущему запросу")
        state = self.license_client._state.load()
        if payload.get("license_id") != state.get("license_id"):
            raise UpdateError("Манифест предназначен другой лицензии")
        correlation_id = payload.get("correlation_id")
        if not isinstance(correlation_id, str) or len(correlation_id) > 128:
            correlation_id = ""
        releases = payload.get("releases")
        if not isinstance(releases, list) or len(releases) > 100:
            raise UpdateError("Сервер вернул некорректный список обновлений")
        valid = [self._parse_release(item, correlation_id) for item in releases]
        newer = [item for item in valid if _version(item.version) > _version(self.current_version)]
        return max(newer, key=lambda item: _version(item.version), default=None)

    def _ensure_update_key(self) -> None:
        if any(key_id in self._public_keys for key_id in ("updates-v1", "updates-v2")):
            return
        try:
            envelope = self.license_client.get_signed_json("/api/v1/releases/key")
            payload = self.license_client.verify_server_payload(envelope)
        except LicenseError as exc:
            raise UpdateError("Не удалось получить ключ подписи обновлений") from exc
        if (
            payload.get("purpose") != "clipart-update-manifest"
            or payload.get("algorithm") != "Ed25519"
            or payload.get("kid") not in {"updates-v1", "updates-v2"}
            or not isinstance(payload.get("public_key"), str)
        ):
            raise UpdateError("Сервер вернул некорректный ключ обновлений")
        self._public_keys["updates-v1"] = _decode_public_key(payload["public_key"])

    def _verify_manifest(self, envelope: object) -> dict[str, object]:
        if not isinstance(envelope, dict) or envelope.get("schema_version") != 1 or envelope.get("algorithm") != "Ed25519":
            raise UpdateError("Формат подписи обновлений не поддерживается")
        key_id = envelope.get("kid")
        payload = envelope.get("payload")
        if not isinstance(key_id, str) or not isinstance(payload, dict):
            raise UpdateError("Сервер вернул повреждённый манифест")
        public_key = self._public_keys.get(key_id)
        if public_key is None:
            raise UpdateError("Неизвестный ключ подписи обновлений")
        try:
            public_key.verify(_decode_signature(envelope.get("signature")), rfc8785.dumps(payload))
        except Exception as exc:
            raise UpdateError("Не удалось проверить подпись обновления") from exc
        return payload

    def _parse_release(self, item: object, correlation_id: str) -> UpdateRelease:
        if not isinstance(item, dict):
            raise UpdateError("Сервер вернул повреждённую ревизию")
        version = item.get("version")
        _version(version)
        if item.get("channel") != "stable" or item.get("platform") != self.platform_id:
            raise UpdateError("Сервер вернул ревизию другого канала или платформы")
        filename = item.get("filename")
        size = item.get("size")
        sha256 = item.get("sha256")
        download_url = item.get("download_url")
        notes = item.get("notes") or ""
        expected_suffix = _PLATFORM_ARTIFACT[self.platform_id][0]
        if (
            not isinstance(filename, str)
            or not _FILENAME.fullmatch(filename)
            or not filename.lower().endswith(expected_suffix)
        ):
            raise UpdateError("Некорректное имя файла обновления")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size > MAX_UPDATE_INSTALLER_BYTES:
            raise UpdateError("Некорректный размер обновления")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise UpdateError("Некорректная контрольная сумма обновления")
        if not isinstance(download_url, str) or len(download_url) > 2048:
            raise UpdateError("Некорректная ссылка обновления")
        self._validate_download_url(download_url)
        if not isinstance(notes, str) or len(notes) > 2000:
            raise UpdateError("Некорректное описание обновления")
        return UpdateRelease(version, filename, size, sha256, download_url, notes, correlation_id)

    def _validate_download_url(self, value: str) -> None:
        base = urlparse(self.license_client._validated_base_url())
        parsed = urlparse(value)
        expected_prefix = base.path.rstrip("/") + "/downloads/"
        if (
            parsed.scheme != "https"
            or parsed.netloc != base.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith(expected_prefix)
        ):
            raise UpdateError("Ссылка обновления не принадлежит лицензионному серверу")

    def cleanup_stale_downloads(self) -> None:
        if not self.download_directory.is_dir():
            return
        for path in self.download_directory.iterdir():
            if path.is_file() and (path.suffix.lower() in {".part", ".exe", ".zip"}):
                try:
                    path.unlink()
                except OSError:
                    continue

    def download(
        self,
        release: UpdateRelease,
        *,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        self._validate_download_url(release.download_url)
        self.download_directory.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            dir=str(self.download_directory), prefix=".update-", suffix=".part"
        )
        os.close(fd)
        temporary = Path(temporary_name)
        final = self.download_directory / release.filename
        digest = hashlib.sha256()
        received = 0
        req = request.Request(
            release.download_url,
            headers={"Accept": _PLATFORM_ARTIFACT[self.platform_id][1]},
            method="GET",
        )
        try:
            opener = request.build_opener(NoRedirectHandler())
            with opener.open(req, timeout=self.timeout) as response, temporary.open("wb") as handle:
                declared = response.headers.get("Content-Length")
                if declared is None or int(declared) != release.size:
                    raise UpdateError("Сервер вернул другой размер обновления")
                while received < release.size:
                    if cancelled is not None and cancelled():
                        raise UpdateError("Скачивание обновления отменено")
                    chunk = response.read(min(1024 * 1024, release.size - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    digest.update(chunk)
                    handle.write(chunk)
                    if progress is not None:
                        progress(received, release.size)
                handle.flush()
                os.fsync(handle.fileno())
            if received != release.size:
                raise UpdateError("Обновление скачано не полностью")
            if not hmac.compare_digest(digest.hexdigest(), release.sha256):
                raise UpdateError("Контрольная сумма обновления не совпадает")
            os.replace(temporary, final)
            return final
        except UpdateError:
            temporary.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise
        except (error.HTTPError, error.URLError, TimeoutError, OSError, ValueError):
            temporary.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            raise UpdateError("Не удалось скачать обновление") from None
