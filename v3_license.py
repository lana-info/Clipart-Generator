"""V3 license activation UI and strict online authorization gate."""

from __future__ import annotations

from typing import Protocol

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from license_client import LicenseAuthorization, LicenseError


class LicenseClientProtocol(Protocol):
    def has_activation(self) -> bool: ...

    def activate(self, license_key: str) -> LicenseAuthorization: ...

    def validate(self) -> LicenseAuthorization: ...


class OnlineLicenseGate:
    """One online-only authorization boundary shared by all V3 modes."""

    def __init__(self, client: LicenseClientProtocol) -> None:
        self.client = client
        self.status_text = "Лицензия не активирована"
        try:
            if client.has_activation():
                self.status_text = "Лицензия сохранена — требуется проверка"
        except LicenseError:
            self.status_text = "Состояние лицензии повреждено"

    def has_activation(self) -> bool:
        try:
            return bool(self.client.has_activation())
        except LicenseError:
            return False

    def activate(self, license_key: str) -> LicenseAuthorization:
        try:
            authorization = self.client.activate(license_key)
        except LicenseError:
            self.status_text = "Лицензия не подтверждена"
            raise
        except Exception:
            self.status_text = "Лицензия не подтверждена"
            raise LicenseError("Не удалось проверить лицензию") from None
        self.status_text = "Лицензия активна"
        return authorization

    def authorize_run(self) -> LicenseAuthorization:
        if not self.has_activation():
            self.status_text = "Лицензия не активирована"
            raise LicenseError("Активируйте лицензию перед запуском")
        try:
            authorization = self.client.validate()
        except LicenseError:
            self.status_text = "Лицензия не подтверждена"
            raise
        except Exception:
            self.status_text = "Лицензия не подтверждена"
            raise LicenseError("Не удалось проверить лицензию") from None
        self.status_text = "Лицензия активна"
        return authorization


class LicenseDialog(QDialog):
    """Transient license-key input; reusable keys are never displayed or stored."""

    def __init__(
        self,
        gate: OnlineLicenseGate,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.gate = gate
        self.setWindowTitle("Лицензия Clipart Generator")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Введите лицензионный ключ. Для активации и каждого запуска требуется интернет."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        self.license_key_input = QLineEdit()
        self.license_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.license_key_input.setPlaceholderText("Лицензионный ключ")
        self.license_key_input.setAccessibleName("Лицензионный ключ")
        form.addRow("Ключ:", self.license_key_input)
        layout.addLayout(form)

        self.status_label = QLabel(gate.status_text)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Активировать")
        self.buttons.accepted.connect(self._activate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _activate(self) -> None:
        license_key = self.license_key_input.text().strip()
        if not license_key:
            self.status_label.setText("Введите лицензионный ключ")
            return
        self.buttons.setEnabled(False)
        try:
            authorization = self.gate.activate(license_key)
        except LicenseError as exc:
            self.license_key_input.clear()
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Лицензия", str(exc))
            return
        finally:
            self.buttons.setEnabled(True)
        self.license_key_input.clear()
        self.status_label.setText(self.gate.status_text)
        QMessageBox.information(
            self,
            "Лицензия",
            f"Лицензия активирована до {authorization.expires_at.astimezone().strftime('%d.%m.%Y %H:%M')}",
        )
        self.accept()
