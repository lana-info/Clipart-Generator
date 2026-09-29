"""Narrow optional extension contract for module-owned result actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol, Sequence


class RunResultsExtension(Protocol):
    export_action_label: str

    def on_edited_output(
        self, state: Any, previous_keys: Sequence[str], destination: Path,
    ) -> None: ...

    def seed_membership(
        self, state: Any, session: Any, export_paths: Sequence[Path],
    ) -> bool: ...

    def export_issues(
        self, state: Any, session: Any, export_paths: Sequence[Path],
    ) -> list[dict[str, Any]]: ...

    def quality_reports(
        self, state: Any, session: Any, export_paths: Sequence[Path],
        requested_paths: Sequence[Path] | None = None,
    ) -> list[Any]: ...

    def create_export_view(
        self, parent: Any, state: Any, paths: Sequence[Path], *,
        review_issues: Sequence[dict[str, Any]], quality_reports: Sequence[Any],
        on_membership_saved: Callable[[Any], None],
        on_fix_requested: Callable[[str], None],
        workspace: Path | None = None, embedded: bool = False,
    ) -> Any | None: ...

    def open_export_dialog(
        self, parent: Any, state: Any, paths: Sequence[Path], *,
        review_issues: Sequence[dict[str, Any]], quality_reports: Sequence[Any],
        on_membership_saved: Callable[[Any], None],
        on_fix_requested: Callable[[str], None],
    ) -> None: ...

    def save_membership(self, state: Any, membership: Any) -> None: ...


__all__ = ["RunResultsExtension"]