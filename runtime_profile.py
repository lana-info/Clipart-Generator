"""Build-time identity and trust. No environment or user-file overrides."""
import base64
from urllib.parse import urlsplit


PRODUCTION_SERVICE = "https://services.etsyneuroclub.com/licenses"
PRODUCTION_LICENSE_KEYS = {"license-v1": "2J5W6NVq8-zE5g0MocublzW5aER1hzRqwFLGuzKuwMw"}


def validate_acceptance_profile(profile):
    if not isinstance(profile, dict) or set(profile) != {"kind", "service_url", "license_keys", "publisher_keys"}:
        raise ValueError("Invalid acceptance profile")
    url = urlsplit(profile["service_url"])
    if (profile["kind"] != "acceptance" or url.scheme != "https" or not url.hostname
            or url.username or url.password or url.query or url.fragment
            or url.path != "/studio-test" or "%" in url.netloc):
        raise ValueError("Acceptance requires a separate HTTPS service")
    for name in ("license_keys", "publisher_keys"):
        keys = profile[name]
        if not isinstance(keys, dict) or not keys or len(keys) > 4:
            raise ValueError("Invalid acceptance trust keys")
        for key_id, value in keys.items():
            if not isinstance(key_id, str) or not key_id or len(key_id) > 128:
                raise ValueError("Invalid acceptance key identity")
            raw = base64.b64decode(value, validate=True)
            if len(raw) != 32:
                raise ValueError("Invalid acceptance public key")
            if name == "license_keys" and raw in {
                base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
                for key in PRODUCTION_LICENSE_KEYS.values()
            }:
                raise ValueError("Acceptance must not trust production license keys")
    return profile


try:
    from _acceptance_build import PROFILE
except ModuleNotFoundError as exc:
    if exc.name != "_acceptance_build":
        raise
    PROFILE = None

IS_ACCEPTANCE = PROFILE is not None
if IS_ACCEPTANCE:
    validate_acceptance_profile(PROFILE)

APP_NAME = "Vibix Studio Test" if IS_ACCEPTANCE else "Vibix Studio"
# Persistent identity must survive the public rename from Images to Studio.
APP_STORAGE_NAME = "Vibix Studio Test" if IS_ACCEPTANCE else "Vibix Images"
LICENSE_SERVICE_BASE_URL = PROFILE["service_url"] if IS_ACCEPTANCE else PRODUCTION_SERVICE
LICENSE_PUBLIC_KEYS = PROFILE["license_keys"] if IS_ACCEPTANCE else PRODUCTION_LICENSE_KEYS
MODULE_PUBLISHER_KEYS = ({name: base64.b64decode(value, validate=True)
                          for name, value in PROFILE["publisher_keys"].items()}
                         if IS_ACCEPTANCE else None)
