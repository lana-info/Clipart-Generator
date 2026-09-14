"""Shared review/preflight presentation for image-generation workflows."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from v3_components import ButtonVariant, DEFAULT_TOKENS, V3Button, V3DesignTokens
from v3_flow_runtime import CostEstimate
from v3_flow_ui import ScrollableStepPage
from v3_image_generation_runtime import (
    estimate_image_generation_cost, fal_endpoint_quantities, image_generation_pipeline_steps,
)

class ImageReviewRunPage(ScrollableStepPage):
    def __init__(
        self,
        common: Any,
        data: Any,
        get_output_dir: Callable[[], str],
        set_output_dir: Callable[[str], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        fal_cost_refresh: Callable[[], tuple[float, str]] | None = None,
    ) -> None:
        super().__init__(
            "Проверка и запуск",
            "Проверьте объём, стоимость и точный порядок до запуска.",
            tokens=tokens,
        )
        self.common = common
        self.data = data
        self._get_output_dir = get_output_dir
        self._set_output_dir = set_output_dir
        self.fal_cost_refresh = fal_cost_refresh
        self._fal_cost_amount: Decimal | None = None
        self._fal_cost_currency = "USD"
        self._fal_cost_signature: tuple[tuple[str, int], ...] | None = None
        self._fal_cost_error = ""
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.output_label.setProperty("v3Status", True)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("v3Status", True)
        self.requests_label = QLabel()
        self.requests_label.setWordWrap(True)
        self.requests_label.setProperty("v3Status", True)
        self.cost_breakdown_label = QLabel()
        self.cost_breakdown_label.setWordWrap(True)
        self.cost_breakdown_label.setProperty("v3Status", True)
        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.pipeline_label.setProperty("v3Status", True)
        self.requirements_label = QLabel()
        self.requirements_label.setWordWrap(True)
        self.requirements_label.setProperty("v3Status", True)
        self.requirements_label.hide()
        self.run_status_label = QLabel()
        self.run_status_label.setWordWrap(True)
        self.run_status_label.setProperty("v3Small", True)
        self.fal_cost_refresh_button = V3Button(
            "Обновить оценку Fal.ai", ButtonVariant.SECONDARY
        )
        self.fal_cost_refresh_button.clicked.connect(self.refresh_fal_cost)
        self.cost_row = QWidget()
        cost_layout = QHBoxLayout(self.cost_row)
        cost_layout.setContentsMargins(0, 0, 0, 0)
        cost_layout.setSpacing(tokens.space_2)
        cost_layout.addWidget(self.cost_breakdown_label)
        cost_layout.addWidget(self.fal_cost_refresh_button)
        cost_layout.addStretch(1)
        for widget in (
            self.output_label,
            self.summary_label,
            self.requests_label,
            self.cost_row,
            self.pipeline_label,
            self.requirements_label,
            self.run_status_label,
        ):
            self.add_widget(widget)
        self.card.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card.content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        for label in (
            self.card.title_label,
            self.card.description_label,
            self.output_label,
            self.summary_label,
            self.requests_label,
            self.cost_breakdown_label,
            self.pipeline_label,
            self.requirements_label,
            self.run_status_label,
        ):
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Maximum,
            )
        self.refresh_from_state()

    def _fal_selected(self) -> bool:
        return bool(fal_endpoint_quantities(self.data))

    def validation_issues(self) -> tuple[str, ...]:
        return ()

    def refresh_from_state(self) -> None:
        output_dir = self._get_output_dir()
        if not output_dir and self.common.work_dir:
            output_dir = str(Path(self.common.work_dir) / "output")
            self._set_output_dir(output_dir)
        if not output_dir:
            output_dir = "не выбрана"
        estimate = estimate_image_generation_cost(self.data)
        fal_signature = tuple(sorted(fal_endpoint_quantities(self.data).items()))
        if self._fal_cost_signature != fal_signature:
            self._fal_cost_amount = None
            self._fal_cost_currency = "USD"
            self._fal_cost_error = ""
        generation = self.data.generation
        self.output_label.setText(f"Папка результата: {output_dir}")
        variants = generation.variants
        model_summary = f"модель {generation.model}"
        output_count = len(self.data.prompts) * variants
        self.summary_label.setText(
            f"Всего изображений {output_count} · {model_summary} · "
            f"формат {generation.ratio} · {generation.resolution}"
        )
        self.requests_label.setText(
            "API-вызовы: "
            f"генерация {estimate.generation_request_count} · "
            f"обработка {estimate.processing_request_count} · "
            f"всего {estimate.request_count}"
        )
        self._render_cost_breakdown(estimate)
        self.pipeline_label.setText(
            "Порядок: "
            + " → ".join(
                image_generation_pipeline_steps(self.data.operations)
            )
        )
        has_fal = self._fal_selected()
        self.fal_cost_refresh_button.setVisible(has_fal)

    def _render_cost_breakdown(self, estimate: CostEstimate) -> None:
        labels = {
            "kie": "KIE",
            "fal": "Fal.ai",
            "photoroom": "PhotoRoom",
        }
        lines = ["Ориентировочная стоимость"]
        total = Decimal("0")
        total_complete = True
        for provider in ("kie", "fal", "photoroom"):
            if provider not in estimate.provider_usd:
                continue
            if provider == "fal":
                if self._fal_cost_amount is not None:
                    lines.append(
                        f"Fal.ai — {self._fal_cost_amount:.3f} "
                        f"{self._fal_cost_currency}"
                    )
                    if self._fal_cost_currency == "USD":
                        total += self._fal_cost_amount
                    else:
                        total_complete = False
                elif self._fal_cost_error:
                    lines.append(f"Fal.ai — {self._fal_cost_error}")
                    total_complete = False
                else:
                    lines.append("Fal.ai — требуется обновить")
                    total_complete = False
                continue
            amount = estimate.provider_usd[provider]
            if provider in estimate.incomplete_providers:
                lines.append(f"{labels[provider]} — стоимость недоступна")
                total_complete = False
            else:
                lines.append(f"{labels[provider]} — {amount:.3f} USD")
                total += amount
        if total_complete:
            lines.append(f"Итого — {total:.3f} USD")
        else:
            lines.append("Итого — не рассчитано полностью")
        lines.append("Фактическая сумма может отличаться.")
        self.cost_breakdown_label.setText("\n".join(lines))

    def refresh_fal_cost(self) -> None:
        current_signature = tuple(
            sorted(fal_endpoint_quantities(self.data).items())
        )
        if self.fal_cost_refresh is None:
            self._fal_cost_amount = None
            self._fal_cost_signature = current_signature
            self._fal_cost_error = "добавьте API-ключ в настройках"
            self._render_cost_breakdown(estimate_image_generation_cost(self.data))
            return
        try:
            amount, currency = self.fal_cost_refresh()
        except (RuntimeError, ValueError, TypeError) as error:
            self._fal_cost_amount = None
            self._fal_cost_signature = current_signature
            self._fal_cost_error = f"не удалось обновить: {error}"
            self._render_cost_breakdown(estimate_image_generation_cost(self.data))
            return
        self._fal_cost_amount = Decimal(str(amount))
        self._fal_cost_currency = str(currency or "USD").upper()
        self._fal_cost_signature = current_signature
        self._fal_cost_error = ""
        self._render_cost_breakdown(estimate_image_generation_cost(self.data))

    def set_preflight_status(self, text: str, *, ready: bool) -> None:
        if ready:
            self.requirements_label.clear()
            self.requirements_label.setVisible(False)
            self.requirements_label.setAccessibleName("")
            return
        self.requirements_label.setVisible(True)
        prefix = "✓ " if ready else "✕ "
        self.requirements_label.setText(prefix + text)
        self.requirements_label.setProperty(
            "state",
            "default" if ready else "error",
        )
        self.requirements_label.setAccessibleName(prefix + text)
    def set_run_status(self, text: str, *, error: bool = False) -> None:
        prefix = "✕ " if error else "✓ "
        self.run_status_label.setText(prefix + text)
        self.run_status_label.setAccessibleName(prefix + text)
