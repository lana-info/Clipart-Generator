"""Small, dependency-free transport guard for credential-bearing calls."""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse


class NetworkSecurityError(RuntimeError):
    pass


class HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        source = urlparse(req.full_url)
        target = urlparse(newurl)
        if target.scheme.lower() != "https" or not target.hostname:
            raise NetworkSecurityError("HTTPS-only redirect blocked")
        if source.scheme.lower() == "https" and (
            target.hostname.casefold() != source.hostname.casefold()
            or target.port != source.port
        ):
            raise NetworkSecurityError("cross-host redirect blocked")
        if target.username or target.password:
            raise NetworkSecurityError("redirect credentials blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def secure_json_request(url: str, *, headers: dict[str, str], timeout: float, max_bytes: int = 256 * 1024, on_response=None):
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise NetworkSecurityError("credential-bearing requests require a clean HTTPS URL")
    request = urllib.request.Request(url, headers=headers, method="GET")
    for key in ("Authorization", "X-Api-Key", "X-api-key"):
        value = request.get_header(key)
        if value:
            request.remove_header(key)
            request.add_unredirected_header(key, value)
    opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
    with opener.open(request, timeout=max(1.0, min(float(timeout), 60.0))) as response:
        if on_response is not None:
            status = getattr(response, "status", None)
            if isinstance(status, int) and not isinstance(status, bool):
                on_response(status)
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise NetworkSecurityError("API response exceeds size limit")
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except (UnicodeError, ValueError) as error:
        raise NetworkSecurityError("API returned malformed JSON") from error
