import json
import os
import uuid
import hashlib
import base64
import stat
from datetime import datetime, timedelta, timezone
from urllib import request, error
from urllib.parse import urlparse


MAX_LICENSE_RESPONSE_BYTES = 2 * 1024 * 1024
LICENSE_SIGNING_KID = "license-v1"
LICENSE_SIGNING_PUBLIC_KEY_B64 = "2J5W6NVq8-zE5g0MocublzW5aER1hzRqwFLGuzKuwMw"


class LicenseHTTPError(RuntimeError):
    def __init__(self, status_code, reason):
        del reason
        self.status_code = int(status_code)
        super().__init__(f"HTTP {self.status_code}")


class NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LicenseClient:
    def __init__(self, server_url, cache_path, app_version, timeout=10, backup_server_url="", device_key_path=""):
        self.server_url = (server_url or "").rstrip("/")
        self.backup_server_url = (backup_server_url or "").rstrip("/")
        self.cache_path = cache_path
        self.app_version = app_version
        self.timeout = timeout
        self.device_key_path = device_key_path or (cache_path + ".device")

    def _device_private_key(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
        try:
            with open(self.device_key_path, "rb") as handle:
                raw = handle.read()
            if len(raw) != 32:
                raise ValueError("invalid device key")
            return Ed25519PrivateKey.from_private_bytes(raw)
        except FileNotFoundError:
            key = Ed25519PrivateKey.generate()
            raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
            os.makedirs(os.path.dirname(self.device_key_path) or ".", exist_ok=True)
            fd = os.open(self.device_key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, raw)
            finally:
                os.close(fd)
            try:
                os.chmod(self.device_key_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
            return key

    def _device_identity(self):
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        key = self._device_private_key()
        public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return key, base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")

    def activate_v1(self, license_key, product_id="clipart-generator"):
        key, device_key = self._device_identity()
        nonce = base64.urlsafe_b64encode(os.urandom(24)).rstrip(b"=").decode("ascii")
        proof = base64.urlsafe_b64encode(key.sign(nonce.encode("utf-8"))).rstrip(b"=").decode("ascii")
        response = self._post_any("/api/v1/licenses/activate", {
            "license_key": (license_key or "").strip(), "product_id": product_id,
            "device_key": device_key, "nonce": nonce, "proof": proof,
            "app_version": self.app_version,
        })
        result = self._unwrap_v1(response)
        result["license_key"] = (license_key or "").strip()
        self._save_cache(result)
        return result

    def validate_v1(self, license_id, product_id="clipart-generator"):
        key, device_key = self._device_identity()
        nonce = base64.urlsafe_b64encode(os.urandom(24)).rstrip(b"=").decode("ascii")
        proof = base64.urlsafe_b64encode(key.sign(nonce.encode("utf-8"))).rstrip(b"=").decode("ascii")
        response = self._post_any("/api/v1/licenses/validate", {
            "license_id": license_id, "product_id": product_id,
            "device_key": device_key, "nonce": nonce, "proof": proof,
            "app_version": self.app_version,
        })
        result = self._unwrap_v1(response)
        self._save_cache(result)
        return result

    @staticmethod
    def _unwrap_v1(response):
        if not isinstance(response, dict) or response.get("schema_version") != 1:
            raise RuntimeError("Сервер лицензий вернул неподписанный ответ")
        if response.get("algorithm") != "Ed25519" or response.get("kid") != LICENSE_SIGNING_KID:
            raise RuntimeError("Неизвестный ключ подписи сервера лицензий")
        payload = response.get("payload")
        signature = response.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature, str):
            raise RuntimeError("Некорректный подписанный ответ сервера лицензий")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        import rfc8785
        public = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(LICENSE_SIGNING_PUBLIC_KEY_B64 + "=" * ((-len(LICENSE_SIGNING_PUBLIC_KEY_B64)) % 4)))
        try:
            public.verify(base64.urlsafe_b64decode(signature + "=" * ((-len(signature)) % 4)), rfc8785.dumps(payload))
        except Exception as exc:
            raise RuntimeError("Не удалось проверить подпись сервера лицензий") from exc
        return {"ok": True, **payload}

    def device_fingerprint(self):
        node = str(uuid.getnode())
        uname = "|".join(os.uname()) if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", "")
        raw = f"{node}|{uname}|clipart-generator"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def activate(self, license_key):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
            "app_version": self.app_version,
        }
        result = self._post_any("/activate", payload)
        if result.get("ok"):
            self._save_cache(result)
        return result

    def validate(self, license_key, use_offline=True):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
            "app_version": self.app_version,
        }
        try:
            result = self._post_any("/validate", payload)
            if result.get("ok"):
                self._save_cache(result)
            return result
        except Exception as e:
            if use_offline:
                offline = self._validate_offline_cache(payload["license_key"], payload["device_fingerprint"])
                if offline.get("ok"):
                    return offline
            return {"ok": False, "message": f"Ошибка проверки лицензии: {e}"}

    def status(self, license_key, use_offline=True):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
            "app_version": self.app_version,
        }
        try:
            result = self._post_any("/status", payload, fallback_paths=["/validate"])
            if result.get("ok"):
                self._save_cache(result)
            return result
        except Exception as e:
            if use_offline:
                offline = self._validate_offline_cache(payload["license_key"], payload["device_fingerprint"])
                if offline.get("ok"):
                    return offline
            return {"ok": False, "message": f"Ошибка проверки статуса лицензии: {e}"}

    def deactivate(self, license_key):
        payload = {
            "license_key": (license_key or "").strip(),
            "device_fingerprint": self.device_fingerprint(),
        }
        result = self._post_any("/deactivate", payload)
        if result.get("ok") and os.path.exists(self.cache_path):
            try:
                os.remove(self.cache_path)
            except Exception:
                pass
        return result

    def _server_urls(self):
        urls = []
        for url in [self.server_url, self.backup_server_url]:
            normalized = (url or "").strip().rstrip("/")
            if normalized and normalized not in urls:
                urls.append(normalized)
        return urls

    def _post_any(self, path, payload, fallback_paths=None):
        urls = self._server_urls()
        if not urls:
            raise RuntimeError("Не указан URL сервера лицензий")

        path_variants = [path]
        for item in fallback_paths or []:
            if item and item not in path_variants:
                path_variants.append(item)

        base_url = urls[0]
        for index, route in enumerate(path_variants):
            try:
                return self._post(base_url, route, payload)
            except LicenseHTTPError as exc:
                has_fallback_route = index + 1 < len(path_variants)
                if exc.status_code in {404, 405} and has_fallback_route:
                    continue
                raise
        raise RuntimeError("Не удалось выполнить запрос к серверу лицензий")

    def _validate_server_url(self, base_url):
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        is_loopback = host in {"localhost", "127.0.0.1", "::1"}
        if parsed.username or parsed.password:
            raise RuntimeError("URL сервера лицензий не должен содержать credentials")
        if parsed.scheme == "https" and host:
            return base_url
        if parsed.scheme == "http" and is_loopback:
            return base_url
        raise RuntimeError("Удалённый сервер лицензий должен использовать HTTPS")

    def _read_response_limited(self, response):
        headers = getattr(response, "headers", None)
        content_length = headers.get("Content-Length") if headers is not None else None
        if content_length:
            try:
                if int(content_length) > MAX_LICENSE_RESPONSE_BYTES:
                    raise RuntimeError("License response exceeds size limit")
            except (TypeError, ValueError):
                pass
        payload = response.read(MAX_LICENSE_RESPONSE_BYTES + 1)
        if len(payload) > MAX_LICENSE_RESPONSE_BYTES:
            raise RuntimeError("License response exceeds size limit")
        return payload

    def _post(self, base_url, path, payload):
        url = f"{self._validate_server_url(base_url)}{path}"
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        opener = request.build_opener(NoRedirectHandler())
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                raw = self._read_response_limited(resp)
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, dict):
                raise RuntimeError("Сервер лицензий вернул некорректный JSON")
            return result
        except error.HTTPError as exc:
            raise LicenseHTTPError(exc.code, exc.reason) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("Не удалось безопасно связаться с сервером лицензий") from exc

    def _save_cache(self, response_payload):
        expires_at = datetime.now(timezone.utc) + timedelta(days=3)
        cache = {
            "license_key": response_payload.get("license_key", ""),
            "license_id": response_payload.get("license_id", ""),
            "device_fingerprint": self.device_fingerprint(),
            "cached_until": expires_at.isoformat(),
            "token": response_payload.get("token", ""),
            "expires_at": response_payload.get("expires_at"),
            "updates_until": response_payload.get("updates_until"),
            "updates_allowed": bool(response_payload.get("updates_allowed", True)),
        }
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

    def _validate_offline_cache(self, license_key, fingerprint):
        if not os.path.exists(self.cache_path):
            return {"ok": False, "message": "Нет офлайн-кеша лицензии"}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("license_key") != license_key:
                return {"ok": False, "message": "Ключ не совпадает с офлайн-кешем"}
            if cache.get("device_fingerprint") != fingerprint:
                return {"ok": False, "message": "Устройство не совпадает с офлайн-кешем"}
            until = datetime.fromisoformat(cache.get("cached_until"))
            if datetime.now(timezone.utc) > until:
                return {"ok": False, "message": "Офлайн-кеш лицензии истёк"}
            return {
                "ok": True,
                "message": "Офлайн-проверка лицензии успешна",
                "offline": True,
                "license_key": cache.get("license_key", ""),
                "token": cache.get("token", ""),
                "expires_at": cache.get("expires_at"),
                "updates_until": cache.get("updates_until"),
                "updates_allowed": bool(cache.get("updates_allowed", True)),
            }
        except Exception as e:
            return {"ok": False, "message": f"Ошибка офлайн-кеша: {e}"}
