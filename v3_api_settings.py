from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from v3_components import ButtonVariant, V3Button


def user_env_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    directory = Path(base) / "Clipart Generator"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / ".env"


def load_credentials(path: Path | None = None) -> dict[str, str]:
    source = path or user_env_path()
    if not source.is_file():
        return {}
    values: dict[str, str] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def save_credentials(values: Mapping[str, str], path: Path | None = None) -> Path:
    destination = path or user_env_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    allowed = {"kie_api_key", "photoroom_api_key", "license_key", "runpod_api_key", "runpod_endpoint_id"}
    content = "".join(
        f"{key}={str(values.get(key) or '').strip()}\n"
        for key in sorted(allowed)
        if str(values.get(key) or "").strip()
    ).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return destination


def check_kie_balance(api_key: str, timeout: float = 15.0) -> str:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Введите KIE API Key")
    request = urllib.request.Request(
        "https://api.kie.ai/api/v1/chat/credit",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(256 * 1024).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        raise RuntimeError("Не удалось проверить баланс KIE") from error
    try:
        import json

        payload: Any = json.loads(raw)
    except ValueError as error:
        raise RuntimeError("KIE вернул неподдерживаемый ответ") from error
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            for name in ("credit", "credits", "balance", "amount"):
                if name in data:
                    return f"Баланс KIE: {data[name]}"
    return "Баланс KIE получен, формат ответа требует уточнения."


class ApiSettingsDialog(QDialog):
    def __init__(self, initial: Mapping[str, str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки API")
        self.setMinimumWidth(560)
        values = dict(load_credentials())
        values.update(initial or {})
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Ключи хранятся локально в пользовательском .env и не показываются в логах."))
        runpod_help = QLabel(
            '<b>RunPod:</b> создайте аккаунт, пополните баланс и Serverless Endpoint; '
            '<a href="https://www.runpod.io/console/user/settings">получить API-ключ</a> · '
            '<a href="https://console.runpod.io/user/billing">открыть баланс и пополнить</a> · '
            '<a href="https://docs.runpod.io/serverless/overview">инструкция Serverless</a> · '
            '<a href="https://www.runpod.io/pricing">цены</a>'
        )
        runpod_help.setOpenExternalLinks(True)
        runpod_help.setWordWrap(True)
        layout.addWidget(runpod_help)
        form = QFormLayout()
        self.kie_edit = QLineEdit(values.get("kie_api_key", ""))
        self.photo_edit = QLineEdit(values.get("photoroom_api_key", ""))
        self.runpod_key_edit = QLineEdit(values.get("runpod_api_key", ""))
        self.runpod_endpoint_edit = QLineEdit(values.get("runpod_endpoint_id", ""))
        for edit in (self.kie_edit, self.photo_edit, self.runpod_key_edit):
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("KIE API Key", self.kie_edit)
        form.addRow("PhotoRoom API Key", self.photo_edit)
        form.addRow("RunPod API Key", self.runpod_key_edit)
        form.addRow("RunPod Endpoint ID", self.runpod_endpoint_edit)
        layout.addLayout(form)
        actions = QVBoxLayout()
        self.balance_button = V3Button("Проверить баланс KIE", ButtonVariant.SECONDARY)
        self.balance_button.clicked.connect(self._check_balance)
        actions.addWidget(self.balance_button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        actions.addWidget(self.status)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.settings: dict[str, str] = {}

    def _check_balance(self) -> None:
        try:
            self.status.setText(check_kie_balance(self.kie_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _save(self) -> None:
        self.settings = {
            "kie_api_key": self.kie_edit.text().strip(),
            "photoroom_api_key": self.photo_edit.text().strip(),
            "runpod_api_key": self.runpod_key_edit.text().strip(),
            "runpod_endpoint_id": self.runpod_endpoint_edit.text().strip(),
        }
        save_credentials(self.settings)
        self.accept()
