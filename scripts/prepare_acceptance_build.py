"""Embed a reviewed public-only profile before building a separate test installer."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_profile import validate_acceptance_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    if args.profile.stat().st_size > 8192:
        parser.error("profile exceeds limit")
    profile = validate_acceptance_profile(json.loads(args.profile.read_text(encoding="utf-8")))
    with (ROOT / "_acceptance_build.py").open("x", encoding="utf-8") as handle:
        handle.write("# Generated public-only acceptance build profile. Never ship as production.\n")
        handle.write("PROFILE = " + repr(profile) + "\n")
    print("Prepared isolated acceptance identity and public trust keys")


if __name__ == "__main__":
    main()
