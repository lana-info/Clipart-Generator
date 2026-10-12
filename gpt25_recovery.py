"""Core confirmation for replacing unavailable GPT Image generation results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fal_provider import FalTaskJournal
from gpt25_provider import generation_payload, provider_for_model


def expired_generation_retries(work_dir, settings, prompts, *, project_id=None):
    """Find only expired receipts matching this project's exact requested inputs."""
    model = str(settings.get("text_generation_model") or "")
    provider = provider_for_model(model)
    if not provider or not prompts:
        return ()
    suffix = f".{project_id}" if project_id else ""
    path = Path(work_dir) / f".vibix_{provider}_tasks{suffix}.json"
    if not path.is_file():
        return ()
    pending = FalTaskJournal(path).pending()
    indices = settings.get("task_item_indices")
    approvals = []
    for index, entry in enumerate(prompts, start=1):
        if entry.get("references"):
            continue
        payload = generation_payload(
            model, entry["prompt"], settings.get("text_generation_ratio", "1:1"),
            settings.get("text_generation_resolution", "1K"),
        )
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        original_index = indices[index - 1] if indices is not None else index
        matching = [task for task in pending if task.model_id == model
                    and task.operation in {"generation", f"generation:{original_index}"}
                    and task.input_fingerprint == fingerprint]
        # Accepted or ambiguous sends must be recovered first, never replaced
        # merely because an older expired receipt is also present.
        if any(task.status != "expired" for task in matching):
            continue
        approvals.extend(f"{provider}:{task.request_id}" for task in matching)
    return tuple(dict.fromkeys(approvals))


def confirm_expired_generation_retries(work_dir, settings, prompts, *, project_id=None, parent=None):
    approvals = expired_generation_retries(work_dir, settings, prompts, project_id=project_id)
    if not approvals:
        return ()
    from PyQt6.QtWidgets import QApplication, QMessageBox

    label = "AtlasCloud" if approvals[0].startswith("atlascloud:") else "PiAPI"
    if parent is None:
        parent = QApplication.activeWindow()
    answer = QMessageBox.question(
        parent, "Результат генерации недоступен",
        f"{label}: прежние результаты больше недоступны ({len(approvals)}).\n"
        "Повтор создаст новые изображения и потребует новой оплаты по текущему тарифу.\n"
        "Запустить новую платную генерацию?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return approvals if answer == QMessageBox.StandardButton.Yes else None
