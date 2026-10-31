"""Signed, licensed Windows update client for the V3 application."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import os
import platform
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping
from urllib import error, request
from urllib.parse import urlparse

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from delivery_signature import (
    DeliveryPolicy,
    DeliverySignatureError,
    enforce_delivery_policy,
)
from license_client import LicenseClient, LicenseError, NoRedirectHandler
from license_update_contract import LicenseUpdatePolicy


MAX_UPDATE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_UPDATE_INSTALLER_BYTES = 512 * 1024 * 1024
PUBLISH_ATTEMPTS = 4          # os.replace свежего файла, пока его держит антивирус (Windows)
PUBLISH_PAUSE_SECONDS = 1.0
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_PLATFORM_ARTIFACT = {
    "windows-x64": (".exe", "application/vnd.microsoft.portable-executable"),
    "macos-arm64": (".zip", "application/zip"),
    "macos-x64": (".zip", "application/zip"),
}


class UpdateError(RuntimeError):
    """Bounded user-safe update failure."""


class _RetryableDownload(Exception):
    """Транзиентный сбой сети/сервера во время скачивания — попытку можно повторить."""


@dataclass(frozen=True)
class UpdateRelease:
    version: str
    filename: str
    size: int
    sha256: str
    download_url: str
    notes: str = ""
    correlation_id: str = ""
    delivery_envelope: dict | None = None


@contextmanager
def _open_protected_artifact(path: Path):
    """Keep a Windows artifact locked against writes/rename through launch."""
    if os.name != "nt":
        with path.open("rb") as handle:
            yield handle
        return

    import ctypes
    import msvcrt

    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    file_attribute_normal = 0x00000080
    file_flag_open_reparse_point = 0x00200000
    file_flag_sequential_scan = 0x08000000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    raw_handle = create_file(
        str(path),
        generic_read,
        file_share_read,
        None,
        open_existing,
        file_attribute_normal
        | file_flag_open_reparse_point
        | file_flag_sequential_scan,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if raw_handle in (None, invalid_handle):
        raise OSError(ctypes.get_last_error(), "Cannot lock update artifact")
    try:
        descriptor = msvcrt.open_osfhandle(raw_handle, os.O_RDONLY)
    except BaseException:
        kernel32.CloseHandle(ctypes.c_void_p(raw_handle))
        raise
    with os.fdopen(descriptor, "rb") as handle:
        yield handle


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
        delivery_public_keys: Mapping[str, str] | None = None,
        delivery_policy: DeliveryPolicy | None = None,
    ) -> None:
        self.license_client = license_client
        self.lifecycle_policy = LicenseUpdatePolicy()
        self.delivery_policy = delivery_policy or DeliveryPolicy()
        self.current_version = current_version
        if platform_id not in _PLATFORM_ARTIFACT:
            raise UpdateError("Эта платформа обновлений не поддерживается")
        self.platform_id = platform_id
        self._artifact_suffix, self._artifact_mime = _PLATFORM_ARTIFACT[platform_id]
        self._artifact_max_bytes = MAX_UPDATE_INSTALLER_BYTES
        self.download_directory = Path(download_directory)
        self.timeout = max(1, min(int(timeout), self.lifecycle_policy.timeout_seconds))
        # Скачивание артефакта (сотни МБ) живёт дольше API-запросов: свой щедрый таймаут
        # на сокет-операцию и мелкие чанки (жалоба владельца 2026-10-31: 243 МБ при
        # 20 с на чанк 1 МБ рвались на медленном канале).
        self._download_timeout = max(self.timeout, int(self.lifecycle_policy.download_timeout_seconds))
        self._public_keys = {
            name: _decode_public_key(value) for name, value in (public_keys or {}).items()
        }
        self._delivery_public_keys = {
            name: _decode_public_key(value)
            for name, value in (delivery_public_keys or {}).items()
        }
        _version(current_version)

    def check(self) -> UpdateRelease | None:
        payload = self._request_manifest("/api/v1/releases/manifest")
        valid = [self._parse_release(item, payload.get("correlation_id", "")) for item in payload["releases"]]
        newer = [item for item in valid if _version(item.version) > _version(self.current_version)]
        return max(newer, key=lambda item: _version(item.version), default=None)

    def _request_manifest(self, path: str, extra: Mapping[str, object] | None = None) -> dict:
        self._ensure_update_key()
        try:
            envelope, device_key, nonce = self.license_client.authenticated_request(
                path,
                {"platform": self.platform_id, "channel": "stable", **(extra or {})},
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
        payload["correlation_id"] = correlation_id
        return payload

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
        self._public_keys[str(payload["kid"])] = _decode_public_key(
            payload["public_key"]
        )

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
        expected_suffix = self._artifact_suffix
        if (
            not isinstance(filename, str)
            or not _FILENAME.fullmatch(filename)
            or not filename.lower().endswith(expected_suffix)
        ):
            raise UpdateError("Некорректное имя файла обновления")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0 or size > self._artifact_max_bytes:
            raise UpdateError("Некорректный размер обновления")
        if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
            raise UpdateError("Некорректная контрольная сумма обновления")
        if not isinstance(download_url, str) or len(download_url) > 2048:
            raise UpdateError("Некорректная ссылка обновления")
        self._validate_download_url(download_url)
        if not isinstance(notes, str) or len(notes) > 2000:
            raise UpdateError("Некорректное описание обновления")
        delivery_envelope = item.get("delivery_manifest")
        if delivery_envelope is not None and not isinstance(delivery_envelope, dict):
            raise UpdateError("Сервер вернул повреждённый подписанный манифест")
        return UpdateRelease(
            version,
            filename,
            size,
            sha256,
            download_url,
            notes,
            correlation_id,
            delivery_envelope,
        )

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
        final = self.download_directory / release.filename
        attempts = max(1, int(self.lifecycle_policy.download_attempts))
        last_message = "Не удалось скачать обновление"
        for attempt in range(1, attempts + 1):
            fd, temporary_name = tempfile.mkstemp(
                dir=str(self.download_directory), prefix=".update-", suffix=".part"
            )
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                self._download_attempt(release, temporary, cancelled=cancelled, progress=progress)
                self._publish_download(temporary, final)
                return final
            except UpdateError:
                temporary.unlink(missing_ok=True)
                raise
            except _RetryableDownload as retry:
                temporary.unlink(missing_ok=True)
                last_message = self._download_error_message(retry.__cause__ or retry)
                if attempt == attempts:
                    break
            except (error.HTTPError, error.URLError, TimeoutError, OSError, ValueError) as exc:
                temporary.unlink(missing_ok=True)
                raise UpdateError(self._download_error_message(exc)) from None
        final.unlink(missing_ok=True)
        raise UpdateError(last_message)

    def _download_attempt(
        self,
        release: UpdateRelease,
        temporary: Path,
        *,
        cancelled: Callable[[], bool] | None,
        progress: Callable[[int, int], None] | None,
    ) -> None:
        """Одна попытка скачать артефакт целиком (исходный поток download)."""
        digest = hashlib.sha256()
        received = 0
        req = request.Request(
            release.download_url,
            headers={"Accept": self._artifact_mime},
            method="GET",
        )
        try:
            opener = request.build_opener(NoRedirectHandler())
            with opener.open(req, timeout=self._download_timeout) as response, temporary.open("wb") as handle:
                declared = response.headers.get("Content-Length")
                if declared is None or int(declared) != release.size:
                    raise UpdateError("Сервер вернул другой размер обновления")
                while received < release.size:
                    if cancelled is not None and cancelled():
                        raise UpdateError("Скачивание обновления отменено")
                    try:
                        chunk = response.read(
                            min(self.lifecycle_policy.download_chunk_bytes, release.size - received)
                        )
                    except (TimeoutError, error.URLError, ConnectionError, http.client.IncompleteRead) as exc:
                        # Транзиентный сбой сети (таймаут, сброс соединения): попытку можно повторить целиком.
                        raise _RetryableDownload() from exc
                    if not chunk:
                        break
                    received += len(chunk)
                    digest.update(chunk)
                    handle.write(chunk)
                    if progress is not None:
                        progress(received, release.size)
                handle.flush()
                os.fsync(handle.fileno())
        except error.HTTPError as exc:
            if 500 <= exc.code < 600:
                raise _RetryableDownload() from exc
            raise UpdateError(f"Сервер обновлений вернул ошибку HTTP {exc.code}.") from None
        except error.URLError as exc:
            raise _RetryableDownload() from exc
        except TimeoutError as exc:
            raise _RetryableDownload() from exc
        if received != release.size:
            raise UpdateError("Обновление скачано не полностью")
        if not hmac.compare_digest(digest.hexdigest(), release.sha256):
            raise UpdateError("Контрольная сумма обновления не совпадает")

    @staticmethod
    def _publish_download(temporary: Path, final: Path) -> None:
        """Перенести скачанный файл на место; Windows на секунды занимает свежий файл сканер/антивирус."""
        for attempt in range(PUBLISH_ATTEMPTS):
            try:
                os.replace(temporary, final)
                return
            except PermissionError:
                if attempt == PUBLISH_ATTEMPTS - 1:
                    raise
                time.sleep(PUBLISH_PAUSE_SECONDS)

    @staticmethod
    def _download_error_message(exc: BaseException) -> str:
        """Причина скачивания — конкретным текстом (правило диагностики AGENTS.md)."""
        reason = getattr(exc, "reason", None)
        if isinstance(exc, PermissionError):
            return ("Файл обновления занят другой программой (часто антивирус проверяет его). "
                    "Подождите минуту и повторите.")
        if isinstance(exc, (TimeoutError, ConnectionError, http.client.IncompleteRead)) or isinstance(reason, TimeoutError):
            return ("Соединение прервалось во время скачивания обновления (канал медленный или нестабильный). "
                    "Попробуйте ещё раз; если повторится — установщик можно скачать вручную.")
        if isinstance(exc, error.HTTPError):
            return f"Сервер обновлений вернул ошибку HTTP {exc.code}."
        if isinstance(exc, error.URLError):
            return "Не удалось соединиться с сервером обновлений."
        return "Не удалось скачать обновление."

    def verify_download(self, release: UpdateRelease, path: str | Path) -> None:
        """Repeat the artifact size and digest checks immediately before launch."""
        with self.protected_download(release, path):
            pass

    @contextmanager
    def protected_download(self, release: UpdateRelease, path: str | Path):
        """Verify and hold the artifact immutable until its launcher returns."""
        artifact = Path(path)
        expected = self.download_directory / release.filename
        try:
            if artifact != expected or artifact.is_symlink() or not artifact.is_file():
                raise UpdateError("Файл обновления не прошёл повторную проверку")
            with _open_protected_artifact(artifact) as handle:
                if os.fstat(handle.fileno()).st_size != release.size:
                    raise UpdateError("Файл обновления не прошёл повторную проверку")
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                if not hmac.compare_digest(digest.hexdigest(), release.sha256):
                    raise UpdateError("Файл обновления не прошёл повторную проверку")
                yield artifact
        except OSError:
            raise UpdateError("Файл обновления не прошёл повторную проверку") from None

    def verify_release_manifest(
        self,
        envelope: object,
        release: UpdateRelease,
        *,
        expected_sha256: str | None = None,
    ) -> dict | None:
        """Verify the service-signed delivery manifest before applying an update.

        The gate is active only while a delivery public key is pinned. With a
        pinned key a missing, unknown or bad manifest signature refuses the
        update, and the verified payload is bound to the exact release row
        accepted by ``check`` and to the digest that was actually measured.
        Returns ``None`` when the policy lets an unverified manifest through.
        """
        try:
            payload = enforce_delivery_policy(
                envelope, self._delivery_public_keys, self.delivery_policy,
            )
        except DeliverySignatureError as exc:
            raise UpdateError(str(exc)) from exc
        if payload is None:
            return None
        if (
            payload.get("version") != release.version
            or payload.get("filename") != release.filename
            or payload.get("sha256") != release.sha256
            or payload.get("download_url") != release.download_url
        ):
            raise UpdateError("Подписанный манифест не соответствует ревизии обновления")
        if expected_sha256 is not None and payload.get("sha256") != expected_sha256:
            raise UpdateError("Подписанный манифест не соответствует скачанному обновлению")
        return payload
