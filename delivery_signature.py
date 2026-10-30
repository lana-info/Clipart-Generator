"""Ed25519 detached-signature contract for release delivery manifests.

The signing key lives only on the license service host (never in this
repository and never in the packaged application; the pipeline receives it
from a CI secret). Applications embed only the matching public key and
refuse to apply a release whose manifest signature does not verify.

The envelope mirrors the shape already trusted by the license/updates
channel (``schema_version`` / ``algorithm`` / ``kid`` / ``payload`` /
``signature``) and signs the RFC 8785 canonical form of the manifest
payload, exactly like ``license_client`` and ``update_client`` do, so one
key model serves the whole delivery chain. The signature is detached:
the payload stays a plain JSON document and the 64-byte Ed25519 signature
travels beside it, base64url encoded without padding.

Privacy rules inherited from the license contract: signing key bytes never
appear in error messages, logs or journal records, and validation failures
report a bounded user-safe reason only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


DELIVERY_SCHEMA_VERSION = 1
DELIVERY_ALGORITHM = "Ed25519"
DEFAULT_DELIVERY_KEY_ID = "delivery-v1"
MAX_MANIFEST_PAYLOAD_BYTES = 64 * 1024
MAX_SIGNATURE_TEXT_LENGTH = 256
MANIFEST_SIGNING_KEY_ENV = "RELEASE_MANIFEST_SIGNING_KEY"
_KEY_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


class DeliverySignatureError(ValueError):
    """A bounded, user-safe signed-manifest failure (no key material)."""


@dataclass(frozen=True)
class DeliveryPolicy:
    """Client policy for applying update manifests.

    ``verify_enabled`` switches the whole delivery-signature gate off (lab /
    dry-run compatibility mode; nothing is verified). With the gate enabled,
    ``reject_unsigned_with_configured_key`` makes the signature mandatory as
    soon as an application pins a delivery public key: a configured key with
    a missing or stripped manifest is a refusal, never a silent fallback.
    """

    verify_enabled: bool = True
    reject_unsigned_with_configured_key: bool = True

    def signature_required(self, *, has_public_key: bool) -> bool:
        return (
            self.verify_enabled
            and self.reject_unsigned_with_configured_key
            and has_public_key
        )


def _canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    if not isinstance(payload, Mapping):
        raise DeliverySignatureError("Манифест доставки должен быть JSON-объектом")
    try:
        canonical = rfc8785.dumps(payload)
    except (TypeError, ValueError) as exc:
        raise DeliverySignatureError("Некорректное содержимое манифеста доставки") from exc
    if not canonical or len(canonical) > MAX_MANIFEST_PAYLOAD_BYTES:
        raise DeliverySignatureError("Манифест доставки превышает допустимый размер")
    return canonical


def encode_key_b64(raw: bytes) -> str:
    """Return raw key/signature bytes as unpadded base64url text."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def public_key_b64(public_key: Ed25519PublicKey) -> str:
    """Return the raw 32-byte public key as unpadded base64url text."""
    return encode_key_b64(public_key.public_bytes_raw())


def decode_signature(value: object) -> bytes:
    if not isinstance(value, str) or not value or len(value) > MAX_SIGNATURE_TEXT_LENGTH:
        raise DeliverySignatureError("Повреждена подпись манифеста доставки")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise DeliverySignatureError("Повреждена подпись манифеста доставки") from exc
    if len(raw) != 64:
        raise DeliverySignatureError("Повреждена подпись манифеста доставки")
    return raw


def sign_manifest_payload(
    payload: Mapping[str, Any],
    private_key: Ed25519PrivateKey,
) -> str:
    """Sign the canonical manifest payload; return a detached base64 signature."""
    canonical = _canonical_payload_bytes(payload)
    return encode_key_b64(private_key.sign(canonical))


def verify_manifest_signature(
    payload: Mapping[str, Any],
    signature: object,
    public_key: Ed25519PublicKey,
) -> None:
    """Verify a detached signature over the canonical payload bytes."""
    canonical = _canonical_payload_bytes(payload)
    raw = decode_signature(signature)
    try:
        public_key.verify(raw, canonical)
    except InvalidSignature as exc:
        raise DeliverySignatureError("Не удалось проверить подпись манифеста доставки") from exc


def build_delivery_envelope(
    payload: Mapping[str, Any],
    private_key: Ed25519PrivateKey,
    *,
    key_id: str = DEFAULT_DELIVERY_KEY_ID,
) -> dict[str, Any]:
    """Wrap a payload and its detached signature into the trusted envelope shape."""
    if not isinstance(key_id, str) or not _KEY_ID_PATTERN.fullmatch(key_id):
        raise DeliverySignatureError("Некорректный идентификатор ключа подписи")
    return {
        "schema_version": DELIVERY_SCHEMA_VERSION,
        "algorithm": DELIVERY_ALGORITHM,
        "kid": key_id,
        "payload": dict(payload),
        "signature": sign_manifest_payload(payload, private_key),
    }


def verify_delivery_envelope(
    envelope: object,
    public_keys: Mapping[str, Ed25519PublicKey],
) -> dict[str, Any]:
    """Verify an envelope against pinned delivery public keys; return the payload."""
    if not isinstance(envelope, Mapping):
        raise DeliverySignatureError("Формат подписанного манифеста не поддерживается")
    if (
        envelope.get("schema_version") != DELIVERY_SCHEMA_VERSION
        or envelope.get("algorithm") != DELIVERY_ALGORITHM
    ):
        raise DeliverySignatureError("Формат подписанного манифеста не поддерживается")
    key_id = envelope.get("kid")
    payload = envelope.get("payload")
    if not isinstance(key_id, str) or not _KEY_ID_PATTERN.fullmatch(key_id):
        raise DeliverySignatureError("Некорректный идентификатор ключа подписи")
    if not isinstance(payload, dict):
        raise DeliverySignatureError("Повреждённый манифест доставки")
    public_key = public_keys.get(key_id) if isinstance(public_keys, Mapping) else None
    if public_key is None:
        raise DeliverySignatureError("Неизвестный ключ подписи манифеста доставки")
    verify_manifest_signature(payload, envelope.get("signature"), public_key)
    return payload


def enforce_delivery_policy(
    envelope: object,
    public_keys: Mapping[str, Ed25519PublicKey],
    policy: DeliveryPolicy,
) -> dict[str, Any] | None:
    """Apply the signed-manifest application policy.

    Returns ``None`` when the delivery gate allows the manifest through
    without verification (policy disabled, no trust anchor pinned, or
    envelope absent in legacy mode). Raises ``DeliverySignatureError`` when
    the policy demands a signature and it is missing, unknown or bad.
    """
    required = policy.signature_required(has_public_key=bool(public_keys))
    present = isinstance(envelope, Mapping) and bool(envelope)
    if not present:
        if required:
            raise DeliverySignatureError("Обновление не сопровождено подписанным манифестом")
        return None
    if not policy.verify_enabled:
        return None
    if not public_keys:
        # No pinned delivery key yet (legacy application): the signature
        # cannot be checked and the policy cannot demand one.
        return None
    return verify_delivery_envelope(envelope, public_keys)


def load_signing_key_file(path: str | Path) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from a protected key file (service side).

    Never prints or logs key bytes; failure messages carry no content.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise DeliverySignatureError("Файл ключа подписи недоступен") from exc
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (ValueError, TypeError) as exc:
        raise DeliverySignatureError("Файл ключа подписи повреждён или защищён паролем") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise DeliverySignatureError("Ключ подписи должен быть Ed25519")
    return key


def load_public_key_file(path: str | Path) -> Ed25519PublicKey:
    """Load an Ed25519 public key from a PEM file (verification side)."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise DeliverySignatureError("Файл публичного ключа подписи недоступен") from exc
    try:
        key = serialization.load_pem_public_key(raw)
    except (ValueError, TypeError) as exc:
        raise DeliverySignatureError("Файл публичного ключа подписи повреждён") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise DeliverySignatureError("Ключ проверки должен быть Ed25519")
    return key


def write_public_key_file(public_key: Ed25519PublicKey, path: str | Path) -> None:
    """Persist the public half of a signing key (service-side provisioning)."""
    payload = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    Path(path).write_bytes(payload)


def _load_pem_private_key_or_fail(key_pem: str) -> Ed25519PrivateKey:
    try:
        key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise DeliverySignatureError("Файл ключа подписи повреждён или защищён паролем") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise DeliverySignatureError("Ключ подписи должен быть Ed25519")
    return key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sign a release delivery manifest or verify its detached signature",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    sign = commands.add_parser("sign", help="Sign a manifest payload JSON")
    sign.add_argument("--payload", required=True, help="Path to the manifest payload JSON")
    sign.add_argument("--key-id", default=DEFAULT_DELIVERY_KEY_ID)
    sign.add_argument("--output", required=True, help="Path for the signed envelope JSON")
    sign.add_argument(
        "--key-env",
        default=MANIFEST_SIGNING_KEY_ENV,
        help="Environment variable holding the PEM private key (never printed)",
    )

    verify = commands.add_parser("verify", help="Verify a signed manifest envelope")
    verify.add_argument("--envelope", required=True, help="Path to the signed envelope JSON")
    verify.add_argument("--public-key-file", required=True, help="Path to the PEM public key")
    verify.add_argument("--artifact-sha256", default=None, help="Expected manifest sha256")

    args = parser.parse_args()
    if args.command == "sign":
        key_pem = os.environ.get(args.key_env, "")
        if not key_pem:
            print(f"SKIP: signing key is not configured ({args.key_env}); manifest stays unsigned")
            return 0
        try:
            private_key = _load_pem_private_key_or_fail(key_pem)
            payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
            envelope = build_delivery_envelope(payload, private_key, key_id=args.key_id)
        except DeliverySignatureError as exc:
            print(str(exc))
            return 1
        except (OSError, UnicodeError, ValueError):
            print("Не удалось прочитать манифест доставки")
            return 1
        output_path = Path(args.output)
        output_path.write_text(
            json.dumps(envelope, ensure_ascii=True, separators=(",", ":")),
            encoding="ascii",
        )
        print(f"SIGNED manifest envelope written to {output_path.name}")
        return 0

    try:
        envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
        public_key = load_public_key_file(args.public_key_file)
        kid = envelope.get("kid") if isinstance(envelope, dict) else None
        if not isinstance(kid, str) or not _KEY_ID_PATTERN.fullmatch(kid):
            raise DeliverySignatureError("Некорректный идентификатор ключа подписи")
        payload = verify_delivery_envelope(envelope, {kid: public_key})
    except (OSError, UnicodeError, ValueError) as exc:
        print(str(exc) if isinstance(exc, DeliverySignatureError)
              else "Не удалось проверить манифест доставки")
        return 1
    expected = args.artifact_sha256
    if expected is not None and str(payload.get("sha256", "")).lower() != expected.lower():
        print("Подписанный манифест не соответствует контрольной сумме артефакта")
        return 1
    print("VERIFIED: manifest signature is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
