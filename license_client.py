"""Online-only desktop client for Clipart License Service."""

from __future__ import annotations

import base64
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping
from urllib import error, request
from urllib.parse import urlparse

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from license_update_contract import LicenseUpdatePolicy


MAX_LICENSE_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_LICENSE_STATE_BYTES = 64 * 1024
OFFLINE_GRACE_DAYS = 7


class LicenseError(RuntimeError):
    """A bounded, user-safe licensing failure."""


class LicenseUnavailableError(LicenseError):
    """A temporary transport/server failure that may be retried safely."""


class NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass(frozen=True)
class LicenseAuthorization:
    license_id: str
    product_id: str
    device_key: str
    issued_at: datetime
    expires_at: datetime
    is_offline_grace: bool = False
    last_verified_at: datetime | None = None
    grace_expires_at: datetime | None = None


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str, *, label: str, expected_length: int | None = None) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise LicenseError(f"Некорректный {label}")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise LicenseError(f"Некорректный {label}") from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise LicenseError(f"Некорректный {label}")
    return decoded


def _parse_datetime(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or len(value) > 128:
        raise LicenseError(f"Некорректный срок лицензии: {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LicenseError(f"Некорректный срок лицензии: {label}") from exc
    if parsed.tzinfo is None:
        raise LicenseError(f"Некорректный срок лицензии: {label}")
    return parsed.astimezone(timezone.utc)


class LicenseStateStore:
    """Atomic, per-user device identity and activation state."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, object]:
        if not self.path.is_file():
            return {}
        try:
            if self.path.stat().st_size > MAX_LICENSE_STATE_BYTES:
                raise LicenseError("Файл состояния лицензии слишком большой")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except LicenseError:
            raise
        except (OSError, UnicodeError, ValueError) as exc:
            raise LicenseError("Не удалось прочитать состояние лицензии") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") not in {1, 2}:
            raise LicenseError("Формат состояния лицензии не поддерживается")
        private_key = _b64decode(
            payload.get("device_private_key"),
            label="закрытый ключ устройства",
            expected_length=32,
        )
        license_id = payload.get("license_id")
        if license_id is not None and (
            not isinstance(license_id, str) or not license_id.strip() or len(license_id) > 128
        ):
            raise LicenseError("Некорректный идентификатор лицензии")
        offline_authorization = payload.get("offline_authorization")
        if offline_authorization is not None and not isinstance(
            offline_authorization,
            dict,
        ):
            raise LicenseError("Состояние автономной лицензии повреждено")
        return {
            "schema_version": int(payload["schema_version"]),
            "device_private_key": private_key,
            "license_id": license_id.strip() if isinstance(license_id, str) else None,
            "offline_authorization": offline_authorization,
        }

    def load_or_create_private_key(self) -> Ed25519PrivateKey:
        state = self.load()
        raw = state.get("device_private_key")
        if isinstance(raw, bytes):
            return Ed25519PrivateKey.from_private_bytes(raw)
        private_key = Ed25519PrivateKey.generate()
        self._write(private_key.private_bytes_raw(), None)
        return private_key

    def save_activation(
        self,
        private_key: Ed25519PrivateKey,
        license_id: str,
        offline_authorization: Mapping[str, object] | None = None,
    ) -> None:
        self._write(
            private_key.private_bytes_raw(),
            license_id,
            offline_authorization,
        )

    def _write(
        self,
        private_key: bytes,
        license_id: str | None,
        offline_authorization: Mapping[str, object] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "device_private_key": _b64encode(private_key),
        }
        if license_id:
            payload["license_id"] = license_id
        if offline_authorization is not None:
            payload["offline_authorization"] = dict(offline_authorization)
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
        ) + "\n"
        if len(encoded.encode("utf-8")) > MAX_LICENSE_STATE_BYTES:
            raise LicenseError("Состояние лицензии превышает допустимый размер")
        fd, temporary = tempfile.mkstemp(
            dir=str(self.path.parent),
            prefix=".license-state.",
            suffix=".tmp",
            text=True,
        )
        try:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(encoded)
            os.replace(temporary, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


class LicenseClient:
    def __init__(
        self,
        base_url: str,
        state_path: str,
        public_keys: Mapping[str, str],
        product_id: str,
        timeout: int = 10,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.product_id = (product_id or "").strip()
        self.lifecycle_policy = LicenseUpdatePolicy()
        self.timeout = max(1, min(int(timeout), self.lifecycle_policy.timeout_seconds))
        if not self.product_id or len(self.product_id) > 128:
            raise LicenseError("Некорректный идентификатор продукта")
        self._public_keys: dict[str, Ed25519PublicKey] = {}
        for key_id, encoded in public_keys.items():
            if not isinstance(key_id, str) or not key_id or len(key_id) > 128:
                raise LicenseError("Некорректный ключ подписи сервера")
            raw = _b64decode(
                encoded,
                label="публичный ключ подписи сервера",
                expected_length=32,
            )
            self._public_keys[key_id] = Ed25519PublicKey.from_public_bytes(raw)
        if not self._public_keys:
            raise LicenseError("Не настроен ключ подписи сервера")
        self._state = LicenseStateStore(state_path)

    def has_activation(self) -> bool:
        return bool(self._state.load().get("license_id"))

    def activate(self, license_key: str) -> LicenseAuthorization:
        normalized_key = (license_key or "").strip()
        if not normalized_key or len(normalized_key) > 128:
            raise LicenseError("Введите корректный лицензионный ключ")
        private_key = self._state.load_or_create_private_key()
        device_key, nonce, proof = self._device_proof(private_key)
        envelope = self._post_json(
            "/api/v1/licenses/activate",
            {
                "product_id": self.product_id,
                "license_key": normalized_key,
                "device_key": device_key,
                "nonce": nonce,
                "proof": proof,
            },
        )
        authorization = self._verify_authorization(envelope, device_key, nonce)
        self._save_online_authorization(
            private_key,
            authorization,
            envelope,
            device_key,
            nonce,
        )
        return authorization

    def validate(self) -> LicenseAuthorization:
        envelope, device_key, nonce = self.authenticated_request(
            "/api/v1/licenses/validate"
        )
        authorization = self._verify_authorization(envelope, device_key, nonce)
        state = self._state.load()
        raw_private = state.get("device_private_key")
        if not isinstance(raw_private, bytes):
            raise LicenseError("Состояние лицензии повреждено")
        self._save_online_authorization(
            Ed25519PrivateKey.from_private_bytes(raw_private),
            authorization,
            envelope,
            device_key,
            nonce,
        )
        return authorization

    def _save_online_authorization(
        self,
        private_key: Ed25519PrivateKey,
        authorization: LicenseAuthorization,
        envelope: Mapping[str, object],
        device_key: str,
        nonce: str,
    ) -> None:
        record: dict[str, object] = {
            "schema_version": 1,
            "license_id": authorization.license_id,
            "product_id": authorization.product_id,
            "device_key": device_key,
            "nonce": nonce,
            "last_verified_at": authorization.issued_at.isoformat(),
            "highest_seen_at": authorization.issued_at.isoformat(),
            "server_envelope": dict(envelope),
        }
        record["device_signature"] = _b64encode(
            private_key.sign(rfc8785.dumps(record))
        )
        self._state.save_activation(
            private_key,
            authorization.license_id,
            record,
        )

    def authorize_offline_grace(
        self,
        *,
        now: datetime | None = None,
    ) -> LicenseAuthorization:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise LicenseError("Некорректное системное время")
        current = current.astimezone(timezone.utc)
        state = self._state.load()
        raw_private = state.get("device_private_key")
        license_id = state.get("license_id")
        record = state.get("offline_authorization")
        if (
            not isinstance(raw_private, bytes)
            or not isinstance(license_id, str)
            or not isinstance(record, dict)
        ):
            raise LicenseError("Нет подтверждённой онлайн-проверки лицензии")

        signed_record = dict(record)
        signature = _b64decode(
            signed_record.pop("device_signature", None),
            label="подпись автономной лицензии",
            expected_length=64,
        )
        private_key = Ed25519PrivateKey.from_private_bytes(raw_private)
        try:
            private_key.public_key().verify(signature, rfc8785.dumps(signed_record))
        except Exception as exc:
            raise LicenseError("Не удалось проверить подпись автономной лицензии") from exc

        if signed_record.get("schema_version") != 1:
            raise LicenseError("Формат автономной лицензии не поддерживается")
        if signed_record.get("license_id") != license_id:
            raise LicenseError("Состояние автономной лицензии повреждено")
        if signed_record.get("product_id") != self.product_id:
            raise LicenseError("Автономная лицензия выдана другому продукту")
        device_key = signed_record.get("device_key")
        nonce = signed_record.get("nonce")
        envelope = signed_record.get("server_envelope")
        if (
            not isinstance(device_key, str)
            or device_key != _b64encode(private_key.public_key().public_bytes_raw())
            or not isinstance(nonce, str)
            or not isinstance(envelope, dict)
        ):
            raise LicenseError("Состояние автономной лицензии повреждено")

        authorization = self._verify_authorization(
            envelope,
            device_key,
            nonce,
            now=current,
            require_current=False,
        )
        if authorization.license_id != license_id:
            raise LicenseError("Состояние автономной лицензии повреждено")
        last_verified_at = _parse_datetime(
            signed_record.get("last_verified_at"),
            label="last_verified_at",
        )
        highest_seen_at = _parse_datetime(
            signed_record.get("highest_seen_at"),
            label="highest_seen_at",
        )
        if last_verified_at != authorization.issued_at:
            raise LicenseError("Состояние автономной лицензии повреждено")
        if current + timedelta(seconds=self.lifecycle_policy.clock_skew_seconds) < highest_seen_at:
            raise LicenseError("Обнаружено некорректное системное время")
        grace_expires_at = last_verified_at + timedelta(days=OFFLINE_GRACE_DAYS)
        if current > grace_expires_at:
            last_check = last_verified_at.astimezone().strftime("%d.%m.%Y %H:%M")
            raise LicenseError(
                "Срок временного автономного доступа завершён\n"
                f"Последняя успешная проверка: {last_check}"
            )

        if current > highest_seen_at:
            signed_record["highest_seen_at"] = current.isoformat()
            signed_record["device_signature"] = _b64encode(
                private_key.sign(rfc8785.dumps(signed_record))
            )
            self._state.save_activation(private_key, license_id, signed_record)
        return LicenseAuthorization(
            license_id=authorization.license_id,
            product_id=authorization.product_id,
            device_key=authorization.device_key,
            issued_at=authorization.issued_at,
            expires_at=authorization.expires_at,
            is_offline_grace=True,
            last_verified_at=last_verified_at,
            grace_expires_at=grace_expires_at,
        )

    def authenticated_request(
        self,
        path: str,
        extra: Mapping[str, str] | None = None,
    ) -> tuple[dict[str, object], str, str]:
        """Post a fresh activated-device proof for a protected client API."""
        if not path.startswith("/api/v1/") or len(path) > 200:
            raise LicenseError("Некорректный путь лицензионного сервиса")
        state = self._state.load()
        license_id = state.get("license_id")
        raw_private = state.get("device_private_key")
        if not isinstance(license_id, str) or not isinstance(raw_private, bytes):
            raise LicenseError("Активируйте лицензию перед запуском")
        private_key = Ed25519PrivateKey.from_private_bytes(raw_private)
        device_key, nonce, proof = self._device_proof(private_key)
        payload = {
            "license_id": license_id,
            "product_id": self.product_id,
            "device_key": device_key,
            "nonce": nonce,
            "proof": proof,
        }
        for name, value in (extra or {}).items():
            if not isinstance(name, str) or not isinstance(value, str) or len(name) > 64 or len(value) > 256:
                raise LicenseError("Некорректные параметры защищённого запроса")
            if name in payload:
                raise LicenseError("Нельзя заменить параметры устройства")
            payload[name] = value
        return self._post_json(path, payload), device_key, nonce

    @staticmethod
    def _device_proof(private_key: Ed25519PrivateKey) -> tuple[str, str, str]:
        device_key = _b64encode(private_key.public_key().public_bytes_raw())
        nonce = secrets.token_urlsafe(32)
        proof = _b64encode(private_key.sign(nonce.encode("utf-8")))
        return device_key, nonce, proof

    def _validated_base_url(self) -> str:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise LicenseError("Некорректный адрес сервера лицензий")
        if parsed.scheme == "https" and host:
            return self.base_url
        if parsed.scheme == "http" and host in {"localhost", "127.0.0.1", "::1"}:
            return self.base_url
        raise LicenseError("Сервер лицензий должен использовать HTTPS")

    def _post_json(self, path: str, payload: dict[str, str]) -> dict[str, object]:
        url = f"{self._validated_base_url()}{path}"
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        opener = request.build_opener(NoRedirectHandler())
        try:
            with opener.open(req, timeout=self.timeout) as response:
                raw = self._read_response_limited(response)
        except error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code not in {408, 425, 429}:
                raise LicenseError("Лицензия отклонена сервером") from None
            if exc.code in {408, 425, 429} or 500 <= exc.code < 600:
                raise LicenseUnavailableError(
                    "Сервер лицензий временно недоступен"
                ) from None
            raise LicenseError("Лицензионный сервер вернул недопустимый ответ") from None
        except (error.URLError, TimeoutError, OSError):
            raise LicenseUnavailableError(
                "Не удалось связаться с сервером лицензий"
            ) from None
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            raise LicenseError("Сервер лицензий вернул некорректный ответ") from None
        if not isinstance(decoded, dict):
            raise LicenseError("Сервер лицензий вернул некорректный ответ")
        return decoded

    def get_signed_json(self, path: str) -> dict[str, object]:
        if not path.startswith("/api/v1/") or len(path) > 200:
            raise LicenseError("Некорректный путь лицензионного сервиса")
        req = request.Request(
            f"{self._validated_base_url()}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        opener = request.build_opener(NoRedirectHandler())
        try:
            with opener.open(req, timeout=self.timeout) as response:
                raw = self._read_response_limited(response)
            envelope = json.loads(raw.decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, OSError, UnicodeError, ValueError):
            raise LicenseError("Не удалось получить подписанные данные сервера") from None
        if not isinstance(envelope, dict):
            raise LicenseError("Сервер вернул некорректный подписанный ответ")
        return envelope

    def verify_server_payload(self, envelope: Mapping[str, object]) -> dict[str, object]:
        if envelope.get("schema_version") != 1 or envelope.get("algorithm") != "Ed25519":
            raise LicenseError("Формат подписи сервера не поддерживается")
        key_id = envelope.get("kid")
        payload = envelope.get("payload")
        if not isinstance(key_id, str) or not isinstance(payload, dict):
            raise LicenseError("Сервер вернул повреждённый подписанный ответ")
        public_key = self._public_keys.get(key_id)
        if public_key is None:
            raise LicenseError("Неизвестный ключ подписи сервера")
        signature = _b64decode(
            envelope.get("signature"),
            label="подпись сервера",
            expected_length=64,
        )
        try:
            public_key.verify(signature, rfc8785.dumps(payload))
        except Exception as exc:
            raise LicenseError("Не удалось проверить подпись сервера") from exc
        return payload

    @staticmethod
    def _read_response_limited(response) -> bytes:
        headers = getattr(response, "headers", None)
        content_length = headers.get("Content-Length") if headers is not None else None
        if content_length is not None:
            try:
                if int(content_length) > MAX_LICENSE_RESPONSE_BYTES:
                    raise LicenseError("Ответ сервера лицензий превышает допустимый размер")
            except (TypeError, ValueError):
                raise LicenseError("Сервер лицензий вернул некорректный размер ответа")
        payload = response.read(MAX_LICENSE_RESPONSE_BYTES + 1)
        if len(payload) > MAX_LICENSE_RESPONSE_BYTES:
            raise LicenseError("Ответ сервера лицензий превышает допустимый размер")
        return payload

    def _verify_authorization(
        self,
        envelope: dict[str, object],
        expected_device_key: str,
        expected_nonce: str,
        *,
        now: datetime | None = None,
        require_current: bool = True,
    ) -> LicenseAuthorization:
        if envelope.get("schema_version") != 1 or envelope.get("algorithm") != "Ed25519":
            raise LicenseError("Формат подписи лицензии не поддерживается")
        key_id = envelope.get("kid")
        payload = envelope.get("payload")
        signature_text = envelope.get("signature")
        if not isinstance(key_id, str) or not isinstance(payload, dict):
            raise LicenseError("Сервер вернул повреждённую лицензию")
        public_key = self._public_keys.get(key_id)
        if public_key is None:
            raise LicenseError("Неизвестный ключ подписи сервера")
        signature = _b64decode(signature_text, label="подпись лицензии", expected_length=64)
        try:
            public_key.verify(signature, rfc8785.dumps(payload))
        except Exception as exc:
            raise LicenseError("Не удалось проверить подпись лицензии") from exc
        if payload.get("product_id") != self.product_id:
            raise LicenseError("Лицензия выдана другому продукту")
        if payload.get("device_key") != expected_device_key:
            raise LicenseError("Лицензия выдана другому устройству")
        if payload.get("nonce") != expected_nonce:
            raise LicenseError("Ответ лицензии содержит неверный nonce")
        license_id = payload.get("license_id")
        if not isinstance(license_id, str) or not license_id.strip() or len(license_id) > 128:
            raise LicenseError("Сервер вернул некорректный идентификатор лицензии")
        issued_at = _parse_datetime(payload.get("issued_at"), label="issued_at")
        expires_at = _parse_datetime(payload.get("expires_at"), label="expires_at")
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise LicenseError("Некорректное системное время")
        current = current.astimezone(timezone.utc)
        if issued_at > current + timedelta(seconds=self.lifecycle_policy.clock_skew_seconds):
            raise LicenseError("Время выдачи лицензии некорректно")
        if require_current and expires_at <= current:
            raise LicenseError("Разрешение лицензии истекло")
        if expires_at <= issued_at:
            raise LicenseError("Срок разрешения лицензии некорректен")
        return LicenseAuthorization(
            license_id=license_id.strip(),
            product_id=self.product_id,
            device_key=expected_device_key,
            issued_at=issued_at,
            expires_at=expires_at,
        )
