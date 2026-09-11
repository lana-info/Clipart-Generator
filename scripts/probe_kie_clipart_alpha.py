"""Bounded four-image KIE probe. No retries of paid submissions.

Only the pinned GPT Image 2 1K tariff is permitted: 6 credits/image ($0.03).
Separate submission/polling and persisted intent prevent blind paid retries.
The supplied key is read from a private temporary file, never logged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import urllib.request
from urllib.parse import urlparse, urlencode

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from network_security import HttpsOnlyRedirectHandler

MODEL = "gpt-image-2-text-to-image"
CREDITS_PER_IMAGE = 6
MAX_REQUESTS = 4
MAX_TOTAL_CREDITS = 24  # $0.12; below the owner's $1 total ceiling.
KEY_PATH = Path("/tmp/vibix-kie-alpha-benchmark.key")
SUBJECTS = {
    "flowers": "a small bouquet of white chamomile, dusty pink cosmos and tiny lavender flowers, with distinct thin solid stems and leaves, tied with an opaque linen bow",
    "wreath": "a circular wreath of sage green leaves and small white and blush pink flowers, with an open empty center and several small gaps between branches",
}


def read_key():
    status = KEY_PATH.lstat()
    if not stat.S_ISREG(status.st_mode) or stat.S_IMODE(status.st_mode) != 0o600:
        raise ValueError("Key must be a regular private 0600 file")
    key = KEY_PATH.read_text(encoding="utf-8-sig").strip()
    if not key or any(character.isspace() for character in key):
        raise ValueError("Invalid credential format")
    return key


def api(key, endpoint, payload=None):
    request = urllib.request.Request(
        "https://api.kie.ai/api/v1/" + endpoint,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    request.add_unredirected_header("Authorization", "Bearer " + key)
    opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
    with opener.open(request, timeout=45) as response:
        raw = response.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError("Oversized API response")
    return json.loads(raw)


def credits(key):
    result = api(key, "chat/credit")
    if result.get("code") != 200 or type(result.get("data")) not in (int, float):
        raise ValueError("Cannot verify balance")
    return float(result["data"])


def prompt(subject, background):
    ending = (
        "Fully transparent empty background with real alpha, no painted white or checkerboard background."
        if background == "native" else
        "Flat solid opaque pure blue #0000FF background, edge-to-edge. No gradient, texture, lighting variation or blue spill on the subject."
    )
    return (
        f"Create one isolated delicate watercolor clipart: {subject}. "
        "Fully opaque solid subject; watercolor texture inside the painted object only. "
        "Complete object centered, at least 10 percent empty margin on every side. "
        "All petals, leaves and thin solid stems distinctly readable and uniformly in focus. "
        "Crisp controlled silhouette, minimal edge antialiasing. "
        "No glass, translucent materials, mesh, smoke, haze, glow, blur, depth of field, "
        "cast shadow, floor, extra objects, text, logo or watermark. " + ending
    )


def save(path, payload):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def submit(folder, key, *, nano=False):
    folder.mkdir(parents=True, exist_ok=False)
    model = "nano-banana-2" if nano else MODEL
    unit_credits = 8 if nano else CREDITS_PER_IMAGE
    request_limit = 1 if nano else MAX_REQUESTS
    reserved = unit_credits * request_limit
    before = credits(key)
    if before < reserved:
        raise ValueError("Insufficient balance for bounded comparison")
    ledger = {"model": model, "tariff_credits_per_image": unit_credits,
              "owner_limit_usd": 1, "reserved_limit_credits": reserved,
              "balance_before": before, "attempts": []}
    subjects = {"flowers": SUBJECTS["flowers"]} if nano else SUBJECTS
    for subject_id, subject in subjects.items():
        for background in (("chroma",) if nano else ("native", "chroma")):
            if (len(ledger["attempts"]) >= request_limit or
                (len(ledger["attempts"]) + 1) * unit_credits > reserved):
                raise ValueError("Budget exhausted")
            balance = credits(key)
            if before - balance > reserved or balance < unit_credits:
                raise ValueError("Balance changed beyond reserved budget")
            item = {"id": f"{subject_id}-{background}", "background_intent": background,
                    "prompt": prompt(subject, background), "state": "submit_intent"}
            ledger["attempts"].append(item)
            save(folder / "ledger.json", ledger)
            try:
                result = api(key, "jobs/createTask", {
                    "model": model,
                    "input": {"prompt": item["prompt"], "aspect_ratio": "1:1", "resolution": "1K"},
                })
                task_id = (result.get("data") or {}).get("taskId")
                if result.get("code") != 200 or not isinstance(task_id, str) or not task_id:
                    message = str(result.get("msg", "")).replace(key, "[redacted]")[:300]
                    item.update(state="rejected_or_unknown", response_code=result.get("code"), server_message=message)
                    save(folder / "ledger.json", ledger)
                    raise ValueError("Submission not confirmed; no retry")
                item.update(state="submitted", task_id=task_id)
                save(folder / "ledger.json", ledger)
                print(item["id"], "submitted", flush=True)
            except Exception:
                # Intent remains durable even if the POST's outcome is unknown.
                raise
    ledger["balance_after_submit"] = credits(key)
    save(folder / "ledger.json", ledger)
    print("Reserved", reserved, "credits. Poll separately.", flush=True)


def download(url, target):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid image URL")
    opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(request, timeout=45) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024:
        raise ValueError("Oversized image")
    with target.open("xb") as output:
        output.write(data)


def poll(folder, key):
    ledger = json.loads((folder / "ledger.json").read_text())
    for item in ledger["attempts"]:
        if item["state"] in ("downloaded", "failed") or not item.get("task_id"):
            continue
        result = api(key, "jobs/recordInfo?" + urlencode({"taskId": item["task_id"]}))
        if result.get("code") != 200:
            print(item["id"], "poll unavailable", flush=True)
            continue
        data = result.get("data") or {}
        state = data.get("state")
        if state == "fail":
            item.update(state="failed", fail_code=data.get("failCode"))
        elif state == "success":
            urls = json.loads(data["resultJson"]).get("resultUrls", [])
            if len(urls) != 1:
                raise ValueError("Unexpected image count")
            path = folder / (item["id"] + ".png")
            if not path.exists():
                download(urls[0], path)
            with Image.open(path) as image:
                alpha = np.asarray(image.convert("RGBA").getchannel("A"))
                item["image"] = {"format": image.format, "mode": image.mode, "size": image.size,
                                 "alpha_min": int(alpha.min()), "alpha_max": int(alpha.max()),
                                 "zero_alpha_fraction": float(np.mean(alpha == 0)),
                                 "partial_alpha_fraction": float(np.mean((alpha > 0) & (alpha < 255))),
                                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            item["state"] = "downloaded"
        print(item["id"], item["state"] if state in ("success", "fail") else state, flush=True)
        save(folder / "ledger.json", ledger)
    ledger["balance_latest"] = credits(key)
    ledger["observed_balance_delta"] = ledger["balance_before"] - ledger["balance_latest"]
    save(folder / "ledger.json", ledger)
    print("Balance delta credits:", ledger["observed_balance_delta"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("submit", "poll", "nano-control"))
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "nano-control":
            submit(args.folder, read_key(), nano=True)
        else:
            {"submit": submit, "poll": poll}[args.action](args.folder, read_key())
    except Exception as error:
        print("Probe stopped:", type(error).__name__, "; inspect ledger; never blindly resubmit", file=sys.stderr)
        raise SystemExit(1)
