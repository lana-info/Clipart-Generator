"""Exercise the isolated deployed test service without displaying test credentials."""
import argparse
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from license_client import LicenseClient
from runtime_profile import validate_acceptance_profile
from studio_module_delivery import StudioModuleDelivery
from v3_license import OnlineLicenseGate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.state_dir.resolve()
    if root.parent != Path("/opt/vibix-studio-acceptance"):
        parser.error("an isolated acceptance state directory is required")
    profile = validate_acceptance_profile(json.loads((root / "public-profile.json").read_text()))
    client_root = root / "smoke-client"
    client_root.mkdir(mode=0o700, exist_ok=True)
    client = LicenseClient(base_url=profile["service_url"], public_keys=profile["license_keys"],
        product_id="clipart-generator", state_path=client_root / "license.json")
    client.activate((root / "smoke-license.txt").read_text().strip())
    delivery = StudioModuleDelivery(root=client_root / "modules", studio_version="3.2.0",
        platform="windows-x64", license_client=client, license_gate=OnlineLicenseGate(client),
        trusted_keys={name: base64.b64decode(value) for name, value in profile["publisher_keys"].items()})
    for module in ("clipart", "processing", "pinterest"):
        release = delivery.check(module)
        if release:
            delivery.install(release)
            delivery.activate(module, release.version)
        else:
            delivery.host.load_active(module)
        assert delivery.has_active_workflow(module)
    print("PASS: real HTTPS activation, manifests, three downloads, signatures and runtime activation")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Acceptance smoke failed:", type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
