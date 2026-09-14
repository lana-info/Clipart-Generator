"""Clipart-owned validation/migration hooks for legacy V3 project state."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from studio_clipart_recipe import ClipartRecipe
import studio_export_membership


class ClipartProjectStateExtension:
    def normalize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        clipart = state.get("clipart")
        if not isinstance(clipart, dict):
            return state
        if "recipe" in clipart:
            clipart["recipe"] = ClipartRecipe.from_dict(clipart["recipe"]).to_dict()
        if "export_membership" in clipart:
            clipart["export_membership"] = studio_export_membership.validate_export_membership(
                clipart["export_membership"]
            )
        return state

    def before_replace(
        self,
        destination: Path,
        state: dict[str, Any],
        *,
        max_bytes: int,
    ) -> None:
        studio_export_membership.backup_membership_migration(destination, state, max_bytes=max_bytes)


__all__ = ["ClipartProjectStateExtension"]
