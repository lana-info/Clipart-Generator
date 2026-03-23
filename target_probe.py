import json
import ssl
import os
import urllib.request
from pathlib import Path


GENERATION_MODELS = [
    ("gpt4o-image", "text_to_image"),
    ("gpt-image/1.5-text-to-image", "text_to_image"),
    ("z-image", "text_to_image"),
    ("google/imagen4", "text_to_image"),
    ("google/imagen4-fast", "text_to_image"),
    ("google/imagen4-ultra", "text_to_image"),
    ("google/nano-banana", "text_to_image"),
    ("flux-2/flex-text-to-image", "text_to_image"),
    ("flux-2/pro-text-to-image", "text_to_image"),
    ("grok-imagine/text-to-image", "text_to_image"),
    ("qwen/text-to-image", "text_to_image"),
    ("nano-banana-pro", "image_to_image"),
    ("flux-2/pro-image-to-image", "image_to_image"),
    ("flux-2/flex-image-to-image", "image_to_image"),
    ("grok-imagine/image-to-image", "image_to_image"),
    ("gpt-image/1.5-image-to-image", "image_to_image"),
    ("qwen/image-to-image", "image_to_image"),
    ("google/nano-banana-edit", "edit"),
    ("qwen/image-edit", "edit"),
]


def get_user_data_dir():
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    user_data_dir = Path(base_dir) / "Clipart Generator"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return user_data_dir


def load_config():
    config_candidates = [
        Path(os.environ.get("CLIPART_GENERATOR_CONFIG", "")).expanduser() if os.environ.get("CLIPART_GENERATOR_CONFIG") else None,
        get_user_data_dir() / "config.json",
        Path(__file__).with_name("config.json"),
    ]
    for config_path in config_candidates:
        if config_path and config_path.is_file():
            return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def post_json(url, headers, payload, timeout=25):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def build_payload(model_name, model_type, sample_url):
    prompt = "simple test image"
    ratio = "1:1"

    if model_name == "gpt4o-image":
        return {"prompt": prompt, "size": ratio}

    if model_name == "gpt-image/1.5-text-to-image":
        return {"prompt": prompt, "aspect_ratio": ratio, "quality": "medium"}

    if model_name == "gpt-image/1.5-image-to-image":
        return {
            "prompt": prompt,
            "input_urls": [sample_url],
            "aspect_ratio": ratio,
            "quality": "medium",
        }

    if model_name in {"flux-2/pro-text-to-image", "flux-2/flex-text-to-image"}:
        return {"prompt": prompt, "aspect_ratio": ratio, "resolution": "1K"}

    if model_name in {"flux-2/pro-image-to-image", "flux-2/flex-image-to-image"}:
        return {
            "prompt": prompt,
            "input_urls": [sample_url],
            "aspect_ratio": ratio,
            "resolution": "1K",
        }

    if model_name == "google/nano-banana":
        return {"prompt": prompt, "image_size": ratio}

    if model_name == "google/nano-banana-edit":
        return {"prompt": prompt, "image_urls": [sample_url], "image_size": ratio}

    if model_name == "qwen/text-to-image":
        return {"prompt": prompt, "image_size": "square_hd"}

    if model_name in {"qwen/image-to-image", "qwen/image-edit"}:
        return {"prompt": prompt, "image_url": sample_url}

    if model_name == "nano-banana-pro":
        return {"prompt": prompt, "image_urls": [sample_url], "aspect_ratio": ratio}

    if model_name in {"grok-imagine/text-to-image", "google/imagen4", "google/imagen4-fast", "google/imagen4-ultra"}:
        return {"prompt": prompt, "aspect_ratio": ratio}

    if model_name == "grok-imagine/image-to-image":
        return {"prompt": prompt, "image_urls": [sample_url], "aspect_ratio": ratio}

    if model_name == "z-image":
        return {"prompt": prompt, "aspect_ratio": ratio}

    if model_type == "text_to_image":
        return {"prompt": prompt, "aspect_ratio": ratio}

    return {"prompt": prompt, "image_urls": [sample_url], "aspect_ratio": ratio}


def main():
    config = load_config()
    api_key = str(os.environ.get("KIE_API_KEY") or config.get("kie_api_key", "")).strip()
    if not api_key:
        raise RuntimeError("Не найден KIE API key. Укажите KIE_API_KEY или сохраните ключ в config.json")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    sample_url = "https://picsum.photos/768/768"
    results = []
    for model_name, model_type in GENERATION_MODELS:
        try:
            payload = build_payload(model_name, model_type, sample_url)
            if model_name == "gpt4o-image":
                response = post_json(
                    "https://api.kie.ai/api/v1/gpt4o-image/generate",
                    headers,
                    payload,
                )
            else:
                response = post_json(
                    "https://api.kie.ai/api/v1/jobs/createTask",
                    headers,
                    {"model": model_name, "input": payload},
                )
            results.append(
                {
                    "model": model_name,
                    "type": model_type,
                    "code": response.get("code"),
                    "msg": response.get("msg"),
                    "taskId": ((response.get("data") or {}).get("taskId")),
                    "payload": payload,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "model": model_name,
                    "type": model_type,
                    "error": str(exc),
                    "payload": payload,
                }
            )

    output_path = Path(__file__).with_name("target_probe_results.json")
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()