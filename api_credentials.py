"""Shared names for provider credentials stored outside regular config."""

import ast
import os
import tempfile

SECRET_CONFIG_KEYS = ("kie_api_key", "photoroom_api_key", "license_key")
ALL_PROVIDER_CREDENTIAL_KEYS = SECRET_CONFIG_KEYS + ("runpod_api_key", "runpod_endpoint_id")


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
            if str(values.get(key, "")).strip()
        ]
        fd, temporary = tempfile.mkstemp(
            dir=os.path.dirname(self.path), prefix=".env.", suffix=".tmp", text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + ("\n" if lines else ""))
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
