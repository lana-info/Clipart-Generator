"""Shared names for provider credentials stored outside regular config."""

import ast
import ctypes
import ctypes.wintypes
import os
import tempfile
from pathlib import Path
from typing import Mapping

SECRET_CONFIG_KEYS = ("kie_api_key", "photoroom_api_key", "fal_api_key")
ALL_PROVIDER_CREDENTIAL_KEYS = SECRET_CONFIG_KEYS + ("runpod_api_key", "runpod_endpoint_id")


class ProtectedCredentialStoreError(RuntimeError):
    pass


class EnvCredentialStore:
    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        if not os.path.exists(self.path):
            return {}
        values: dict[str, str] = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, raw_value = line.split("=", 1)
                    key = key.strip()
                    if not key:
                        continue
                    value = raw_value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                        try:
                            value = ast.literal_eval(value)
                        except Exception:
                            value = value[1:-1]
                    values[key] = value
        except (OSError, UnicodeError):
            return {}
        return values

    def save(self, values: dict[str, str]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lines = [
            f"{key}={str(values.get(key, '')).strip()}"
            for key in ALL_PROVIDER_CREDENTIAL_KEYS
            if key != "fal_api_key" and str(values.get(key, "")).strip()
        ]
        fd, temporary = tempfile.mkstemp(
            dir=os.path.dirname(self.path), prefix=".env.", suffix=".tmp", text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + ("\n" if lines else ""))
                handle.flush()
                if os.name != "nt":
                    os.fchmod(handle.fileno(), 0o600)
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


class ProtectedFalCredentialStore:
    """Store the Fal key outside plaintext config using Windows DPAPI.

    Fal is intentionally unavailable for persistent BYOK on platforms where
    this store is not implemented yet. A caller may still use a server-side
    gateway there without changing this interface.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _protect(value: str) -> bytes:
        if os.name != "nt":
            raise ProtectedCredentialStoreError(
                "Fal.ai key requires a protected OS credential store or gateway"
            )
        raw = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        data_in = _WindowsDataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        data_out = _WindowsDataBlob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            raise ProtectedCredentialStoreError("Windows DPAPI не смог зашифровать Fal.ai key")
        try:
            return ctypes.string_at(data_out.pbData, data_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(data_out.pbData)

    @staticmethod
    def _unprotect(value: bytes) -> str:
        if os.name != "nt":
            raise ProtectedCredentialStoreError(
                "Fal.ai key requires a protected OS credential store or gateway"
            )
        encoded = ctypes.create_string_buffer(value)
        data_in = _WindowsDataBlob(len(value), ctypes.cast(encoded, ctypes.POINTER(ctypes.c_byte)))
        data_out = _WindowsDataBlob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            raise ProtectedCredentialStoreError("Windows DPAPI не смог расшифровать Fal.ai key")
        try:
            return ctypes.string_at(data_out.pbData, data_out.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(data_out.pbData)

    def load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            return {"fal_api_key": self._unprotect(self.path.read_bytes())}
        except (OSError, UnicodeError, ProtectedCredentialStoreError):
            return {}

    def save(self, values: Mapping[str, str]) -> None:
        key = str(values.get("fal_api_key", "") or "").strip()
        if not key:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return
        encrypted = self._protect(key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=str(self.path.parent), prefix=".fal.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


class ProviderCredentialStore:
    """Composite store: legacy providers in .env, Fal in protected storage."""

    def __init__(self, env_path: str | Path, fal_path: str | Path) -> None:
        self.env = EnvCredentialStore(str(env_path))
        self.fal = ProtectedFalCredentialStore(fal_path)

    def load(self) -> dict[str, str]:
        values = self.env.load()
        values.pop("fal_api_key", None)
        values.update(self.fal.load())
        return values

    def save(self, values: Mapping[str, str]) -> None:
        env_values = {key: value for key, value in values.items() if key != "fal_api_key"}
        self.fal.save(values)
        self.env.save(dict(env_values))


if os.name == "nt":
    class _WindowsDataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
else:
    class _WindowsDataBlob:  # pragma: no cover - Windows-only implementation guard
        def __init__(self, *_args, **_kwargs):
            raise ProtectedCredentialStoreError("Windows DPAPI unavailable")
