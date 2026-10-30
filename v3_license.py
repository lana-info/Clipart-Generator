"""V3 license activation UI and strict online authorization gate."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from license_client import (
    LicenseAuthorization,
    LicenseError,
    LicenseUnavailableError,
    safe_license_error_code,
)
from app_identity import APP_NAME


class LicenseClientProtocol(Protocol):
    def has_activation(self) -> bool: ...

    def activate(self, license_key: str) -> LicenseAuthorization: ...

    def validate(self) -> LicenseAuthorization: ...

    def authorize_offline_grace(self) -> LicenseAuthorization: ...


class OnlineLicenseGate:
    """Online-first authorization boundary with bounded outage-only grace."""

    def __init__(self, client: LicenseClientProtocol) -> None:
        self.client = client
        self.current_authorization: LicenseAuthorization | None = None
        self._session_authorization: LicenseAuthorization | None = None
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

    @property
    def verification_text(self) -> str:
        authorization = self.current_authorization
        if authorization is None:
            return "Онлайн-проверка не выполнена"
        if (
            authorization.is_offline_grace
            and authorization.last_verified_at is not None
            and authorization.grace_expires_at is not None
        ):
            checked_at = authorization.last_verified_at.astimezone().strftime(
                "%d.%m.%Y %H:%M"
            )
            grace_end = authorization.grace_expires_at.astimezone().strftime(
                "%d.%m.%Y"
            )
            return f"Последняя проверка: {checked_at}  •  Доступ до: {grace_end}"
        checked_at = authorization.issued_at.astimezone().strftime("%d.%m.%Y %H:%M")
        return f"Проверено онлайн: {checked_at}"

    def activate(self, license_key: str) -> LicenseAuthorization:
        try:
            authorization = self.client.activate(license_key)
        except LicenseError:
            self.current_authorization = None
            self.status_text = "Лицензия не подтверждена"
            raise
        except Exception:
            self.current_authorization = None
            self.status_text = "Лицензия не подтверждена"
            raise LicenseUnavailableError("Не удалось проверить лицензию") from None
        self._session_authorization = self._for_session(authorization)
        self.current_authorization = self._session_authorization
        self.status_text = "Лицензия активна"
        return self._session_authorization

    @staticmethod
    def _for_session(authorization: LicenseAuthorization) -> LicenseAuthorization:
        """Hold a verified online authorization until its module grants end.

        Owner decision 2026-10-23: the licence is verified online once (startup or
        activation), not again while the application works. The server signs each
        authorization for only ~5 minutes, so the in-memory copy is valid for the
        longest module grant it carries. The signature was verified on receipt.
        """
        ends = [grant.expires_at for grant in authorization.module_entitlements]
        if authorization.is_offline_grace or not ends or max(ends) <= authorization.expires_at:
            return authorization
        return replace(authorization, expires_at=max(ends))

    def authorize_run(self) -> LicenseAuthorization:
        session = self._session_authorization
        if session is not None and self.has_activation():
            self.current_authorization = session
            return session
        self._session_authorization = None
        if not self.has_activation():
            self.current_authorization = None
            self.status_text = "Лицензия не активирована"
            raise LicenseError("Активируйте лицензию перед запуском")
        try:
            authorization = self.client.validate()
        except LicenseUnavailableError:
            try:
                authorization = self.client.authorize_offline_grace()
            except LicenseError as exc:
                self.current_authorization = None
                self.status_text = "Требуется подключение"
                raise LicenseUnavailableError(str(exc)) from None
        except LicenseError:
            self.current_authorization = None
            self.status_text = "Лицензия не подтверждена"
            raise
        except Exception:
            self.current_authorization = None
            self.status_text = "Лицензия не подтверждена"
            raise LicenseUnavailableError("Не удалось проверить лицензию") from None
        if not authorization.is_offline_grace:
            authorization = self._for_session(authorization)
            self._session_authorization = authorization
        self.current_authorization = authorization
        self.status_text = (
            "Временный автономный доступ"
            if authorization.is_offline_grace
            else "Лицензия активна"
        )
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
        self.setWindowTitle(f"Лицензия {APP_NAME}")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        description = QLabel(
            "Введите лицензионный ключ. Для первой активации требуется интернет."
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

        # A safe support code (no key, no personal data) for a failed activation — approved mockup H.
        self.error_code_label = QLabel()
        self.error_code_label.setStyleSheet("color:#f5b45a;font-weight:bold")
        self.error_code_label.setAccessibleName("Код ошибки лицензии")
        self.error_code_label.hide()
        layout.addWidget(self.error_code_label)
        self.copy_error_button = QPushButton("Скопировать код ошибки")
        self.copy_error_button.clicked.connect(self._copy_error_code)
        self.copy_error_button.hide()
        layout.addWidget(self.copy_error_button)
        self._error_code = ""

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Активировать")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        self.buttons.accepted.connect(self._activate)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _show_error_code(self, code: str) -> None:
        self._error_code = code
        self.error_code_label.setText(f"Код ошибки: {code}" if code else "")
        self.error_code_label.setVisible(bool(code))
        self.copy_error_button.setVisible(bool(code))

    def _copy_error_code(self) -> None:
        if self._error_code:
            QApplication.clipboard().setText(self._error_code)

    def _activate(self) -> None:
        license_key = self.license_key_input.text().strip()
        if not license_key:
            self.status_label.setText("Введите лицензионный ключ")
            return
        self.buttons.setEnabled(False)
        try:
            self.gate.activate(license_key)
        except LicenseError as exc:
            self.license_key_input.clear()
            self.status_label.setText(str(exc))
            self._show_error_code(safe_license_error_code(exc))
            QMessageBox.warning(self, "Лицензия", f"{exc}\n\nКод ошибки: {self._error_code}")
            return
        finally:
            self.buttons.setEnabled(True)
        self._show_error_code("")
        self.license_key_input.clear()
        self.status_label.setText(self.gate.status_text)
        QMessageBox.information(
            self,
            "Лицензия",
            "Лицензия активирована и проверена онлайн",
        )
        self.accept()


class SavedLicenseUnavailableDialog(QDialog):
    """Fail-closed retry UI after grace is unavailable or expired."""

    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Лицензия {APP_NAME}")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        title = QLabel("Нужно восстановить соединение")
        title.setProperty("v3Title", True)
        layout.addWidget(title)
        description = QLabel(
            "Срок временного автономного доступа завершён. Чтобы продолжить "
            "работу, подключитесь к интернету и повторите проверку лицензии."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        safe_message = str(message or "Сервер лицензий временно недоступен")[:300]
        status_text = next(
            (
                line
                for line in safe_message.splitlines()
                if line.startswith("Последняя успешная проверка:")
            ),
            safe_message,
        )
        self.status_label = QLabel(status_text)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.buttons = QDialogButtonBox()
        retry_button = self.buttons.addButton(
            "Повторить проверку",
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        close_button = self.buttons.addButton(
            "Закрыть",
            QDialogButtonBox.ButtonRole.RejectRole,
        )
        retry_button.clicked.connect(self.accept)
        close_button.clicked.connect(self.reject)
        layout.addWidget(self.buttons)
