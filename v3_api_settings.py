from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
import json
from pathlib import Path
from typing import Any, Mapping

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from v3_components import ButtonVariant, V3Button
from api_credentials import ALL_PROVIDER_CREDENTIAL_KEYS, ProviderCredentialStore
from provider_clients import check_kie_balance, check_photoroom_balance
from app_identity import APP_NAME
from runtime_settings import PROVIDER_CONCURRENCY_CHOICES, normalize_provider_concurrency


def _fal_platform_request(
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    params: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Введите Fal.ai API Key")
    url = f"https://api.fal.ai/v1/{path.lstrip('/')}"
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode(params)
    body = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Key {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        opener = urllib.request.build_opener()
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(512 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise RuntimeError("Fal.ai отклонил ключ или у ключа недостаточно прав") from error
        if error.code == 429:
            raise RuntimeError("Fal.ai временно ограничил частоту запросов") from error
        raise RuntimeError(f"Fal.ai не вернул данные ({error.code})") from error
    except (urllib.error.URLError, OSError) as error:
        raise RuntimeError("Не удалось обратиться к Fal.ai") from error
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise RuntimeError("Fal.ai вернул неподдерживаемый ответ") from error
    if not isinstance(result, dict):
        raise RuntimeError("Fal.ai вернул неожиданный формат ответа")
    return result


def check_fal_balance(api_key: str, timeout: float = 15.0) -> str:
    payload = _fal_platform_request(
        api_key,
        "account/billing",
        params={"expand": "credits"},
        timeout=timeout,
    )
    credits = payload.get("credits")
    if not isinstance(credits, Mapping) or "current_balance" not in credits:
        raise RuntimeError("Fal.ai вернул баланс в неподдерживаемом формате")
    currency = str(credits.get("currency") or "USD").upper()
    return f"Баланс Fal.ai: {credits['current_balance']} {currency}"


def fetch_fal_pricing(
    api_key: str,
    endpoint_ids: str | list[str] | tuple[str, ...],
    timeout: float = 15.0,
) -> tuple[dict[str, Any], ...]:
    if isinstance(endpoint_ids, str):
        endpoint_ids = (endpoint_ids,)
    normalized = tuple(str(endpoint).strip() for endpoint in endpoint_ids if str(endpoint).strip())
    if not normalized or len(normalized) > 50:
        raise ValueError("Укажите от 1 до 50 Fal.ai endpoint ID")
    payload = _fal_platform_request(
        api_key,
        "models/pricing",
        params={"endpoint_id": ",".join(normalized)},
        timeout=timeout,
    )
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise RuntimeError("Fal.ai вернул цены в неподдерживаемом формате")
    return tuple(item for item in prices if isinstance(item, dict))


def estimate_fal_cost(
    api_key: str,
    endpoint_quantities: Mapping[str, int],
    timeout: float = 15.0,
) -> tuple[float, str]:
    quantities = {
        str(endpoint).strip(): int(quantity)
        for endpoint, quantity in endpoint_quantities.items()
        if str(endpoint).strip() and int(quantity) > 0
    }
    if not quantities:
        raise ValueError("Укажите количество Fal.ai вызовов")
    payload = _fal_platform_request(
        api_key,
        "models/pricing/estimate",
        method="POST",
        payload={
            "estimate_type": "historical_api_price",
            "endpoints": {endpoint: {"call_quantity": quantity} for endpoint, quantity in quantities.items()},
        },
        timeout=timeout,
    )
    try:
        return float(payload["total_cost"]), str(payload.get("currency") or "USD").upper()
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Fal.ai вернул оценку стоимости в неподдерживаемом формате") from error


def user_env_path() -> Path:
    if sys.platform == "darwin":
        directory = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        directory = Path(base) / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory / ".env"


def user_fal_key_path() -> Path:
    return user_env_path().with_name("fal_api_key.bin")


def load_credentials(path: Path | None = None) -> dict[str, str]:
    env_path = path or user_env_path()
    return ProviderCredentialStore(
        env_path,
        env_path.with_name("fal_api_key.bin"),
    ).load()


def save_credentials(values: Mapping[str, str], path: Path | None = None) -> Path:
    destination = path or user_env_path()
    ProviderCredentialStore(
        destination,
        destination.with_name("fal_api_key.bin"),
    ).save(
        {
            key: str(values.get(key) or "").strip()
            for key in ALL_PROVIDER_CREDENTIAL_KEYS
        }
    )
    return destination


def _legacy_check_kie_balance(api_key: str, timeout: float = 15.0) -> str:
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
    def __init__(self, initial: Mapping[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки API")
        self.setMinimumWidth(560)
        values = dict(load_credentials())
        values.update(initial or {})
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Ключи KIE/PhotoRoom хранятся локально в пользовательском .env; "
                "Fal.ai сохраняется в защищённом хранилище Windows и не показывается в логах."
            )
        )
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
        provider_help = QLabel(
            '<b>Пополнение и управление:</b> '
            '<a href="https://kie.ai/billing">KIE Billing</a> · '
            '<a href="https://kie.ai/api-key">KIE API Key</a> · '
            '<a href="https://www.photoroom.com/api">PhotoRoom API</a> · '
            '<a href="https://docs.photoroom.com/getting-started/pricing">PhotoRoom тарифы и кредиты</a>'
        )
        provider_help.setOpenExternalLinks(True)
        provider_help.setWordWrap(True)
        layout.addWidget(provider_help)
        form = QFormLayout()
        self.kie_edit = QLineEdit(values.get("kie_api_key", ""))
        self.photo_edit = QLineEdit(values.get("photoroom_api_key", ""))
        self.fal_edit = QLineEdit(values.get("fal_api_key", ""))
        self.runpod_key_edit = QLineEdit(values.get("runpod_api_key", ""))
        self.runpod_endpoint_edit = QLineEdit(values.get("runpod_endpoint_id", ""))
        for edit in (self.kie_edit, self.photo_edit, self.fal_edit, self.runpod_key_edit):
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        kie_row = QHBoxLayout()
        kie_row.addWidget(self.kie_edit)
        self.balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.balance_button.clicked.connect(self._check_balance)
        kie_row.addWidget(self.balance_button)
        form.addRow("KIE API Key", kie_row)
        photo_row = QHBoxLayout()
        photo_row.addWidget(self.photo_edit)
        self.photo_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.photo_balance_button.clicked.connect(self._check_photoroom_balance)
        photo_row.addWidget(self.photo_balance_button)
        form.addRow("PhotoRoom API Key", photo_row)
        fal_row = QHBoxLayout()
        fal_row.addWidget(self.fal_edit)
        self.fal_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.fal_balance_button.clicked.connect(self._check_fal_balance)
        fal_row.addWidget(self.fal_balance_button)
        form.addRow("Fal.ai API Key", fal_row)
        form.addRow("RunPod API Key", self.runpod_key_edit)
        form.addRow("RunPod Endpoint ID", self.runpod_endpoint_edit)
        self.kie_concurrency_combo = QComboBox()
        for concurrency in PROVIDER_CONCURRENCY_CHOICES:
            self.kie_concurrency_combo.addItem(str(concurrency), concurrency)
        selected_concurrency = normalize_provider_concurrency(
            values.get("kie_concurrency"),
            legacy_value=values.get("generation_concurrency"),
        )
        self.kie_concurrency_combo.setCurrentIndex(
            self.kie_concurrency_combo.findData(selected_concurrency)
        )
        form.addRow("Одновременных задач KIE", self.kie_concurrency_combo)
        self.photoroom_concurrency_combo = QComboBox()
        for concurrency in PROVIDER_CONCURRENCY_CHOICES:
            self.photoroom_concurrency_combo.addItem(str(concurrency), concurrency)
        selected_photoroom_concurrency = normalize_provider_concurrency(
            values.get("photoroom_concurrency")
        )
        self.photoroom_concurrency_combo.setCurrentIndex(
            self.photoroom_concurrency_combo.findData(selected_photoroom_concurrency)
        )
        form.addRow("Одновременных задач PhotoRoom", self.photoroom_concurrency_combo)
        self.fal_concurrency_combo = QComboBox()
        for concurrency in PROVIDER_CONCURRENCY_CHOICES:
            self.fal_concurrency_combo.addItem(str(concurrency), concurrency)
        selected_fal_concurrency = normalize_provider_concurrency(
            values.get("fal_concurrency")
        )
        self.fal_concurrency_combo.setCurrentIndex(
            self.fal_concurrency_combo.findData(selected_fal_concurrency)
        )
        form.addRow("Одновременных задач Fal.ai", self.fal_concurrency_combo)
        layout.addLayout(form)
        actions = QVBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        actions.addWidget(self.status)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.settings: dict[str, Any] = {}

    def _check_balance(self) -> None:
        try:
            self.status.setText(check_kie_balance(self.kie_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _check_photoroom_balance(self) -> None:
        try:
            self.status.setText(check_photoroom_balance(self.photo_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _check_fal_balance(self) -> None:
        try:
            self.status.setText(check_fal_balance(self.fal_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _save(self) -> None:
        self.settings = {
            "kie_api_key": self.kie_edit.text().strip(),
            "photoroom_api_key": self.photo_edit.text().strip(),
            "fal_api_key": self.fal_edit.text().strip(),
            "runpod_api_key": self.runpod_key_edit.text().strip(),
            "runpod_endpoint_id": self.runpod_endpoint_edit.text().strip(),
            "kie_concurrency": normalize_provider_concurrency(
                self.kie_concurrency_combo.currentData()
            ),
            "photoroom_concurrency": normalize_provider_concurrency(
                self.photoroom_concurrency_combo.currentData()
            ),
            "fal_concurrency": normalize_provider_concurrency(
                self.fal_concurrency_combo.currentData()
            ),
        }
        save_credentials(
            {
                key: value
                for key, value in self.settings.items()
                if key in ALL_PROVIDER_CREDENTIAL_KEYS
            }
        )
        self.accept()
