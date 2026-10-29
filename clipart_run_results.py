"""Clipart-owned result membership, bundle export, and alpha-QC actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from result_background_policy import keeps_background
import studio_alpha_qc
from studio_bundle_planner import validate_bundle_plan
from studio_clipart_recipe import ClipartRecipe
from studio_export_membership import (
    asset_id_for_path,
    validate_export_membership,
)
from studio_set_export_ui import SetExportDialog


def _succeeded(item: Any) -> bool:
    return getattr(getattr(item, "status", None), "value", None) == "succeeded"


def _resolved(value: Any) -> str:
    try:
        return str(Path(str(value)).resolve())
    except OSError:
        return ""


def _clipart_data(state: Any):
    try:
        return state.data
    except AttributeError:
        try:
            return state.clipart
        except AttributeError as exc:
            raise TypeError("state must expose Clipart workflow data") from exc


def _name_translator():
    try:
        from studio_name_translation import build_name_translator
        return build_name_translator()
    except Exception:
        return None


class ClipartRunResultsExtension:
    export_action_label = "Экспорт наборов ZIP"

    def __init__(self, *, collections_enabled: bool = True) -> None:
        self.collections_enabled = collections_enabled
        if not collections_enabled:
            self.export_action_label = ""

    def on_edited_output(
        self, state: Any, previous_keys: Sequence[str], destination: Path,
    ) -> None:
        membership = _clipart_data(state).export_membership
        previous = None
        for key in previous_keys:
            previous = membership.get(str(key))
            if previous is not None:
                break
        if previous is None:
            return
        membership = validate_export_membership(membership)
        previous = None
        for key in previous_keys:
            previous = membership.get(str(key))
            if previous is not None:
                break
        if previous is None:
            return
        membership[str(destination)] = dict(
            previous,
            memberships=[dict(link) for link in previous["memberships"]],
        )
        _clipart_data(state).export_membership = validate_export_membership(membership)

    def _recipe_plan(self, state: Any):
        if not self.collections_enabled:
            return None
        recipe_data = _clipart_data(state).recipe
        if not isinstance(recipe_data, dict):
            return None
        recipe = ClipartRecipe.from_dict(recipe_data)
        return recipe, validate_bundle_plan(recipe.bundle_plan, recipe.objects)
    def seed_membership(
        self, state: Any, session: Any, export_paths: Sequence[Path],
    ) -> bool:
        try:
            recipe_and_plan = self._recipe_plan(state)
            if recipe_and_plan is None:
                return False
            _recipe, plan = recipe_and_plan
            membership = validate_export_membership(_clipart_data(state).export_membership)
        except (TypeError, ValueError):
            return False
        exported = {str(path.resolve()) for path in export_paths}
        by_object: dict[str, set[str]] = {}
        for item in session.items:
            if not _succeeded(item) or not item.output_path or not isinstance(item.payload, dict):
                continue
            object_id = str(item.payload.get("object_id") or "").strip()
            resolved = _resolved(item.output_path)
            if object_id and resolved in exported:
                by_object.setdefault(object_id, set()).add(resolved)
        changed = False
        for object_id, outputs in by_object.items():
            if len(outputs) != 1:
                continue
            path = next(iter(outputs))
            if path in membership:
                continue
            links = [
                {"set_id": row["set_id"], "title": row["title"], "included": True}
                for row in plan["sets"] if object_id in row["item_ids"]
            ]
            if not links:
                continue
            candidate = dict(membership)
            candidate[path] = {
                "version": 2,
                "asset_id": asset_id_for_path(path),
                "memberships": links,
            }
            membership = validate_export_membership(candidate)
            changed = True
        if changed:
            _clipart_data(state).export_membership = membership
        return changed

    def export_issues(
        self, state: Any, session: Any, export_paths: Sequence[Path],
    ) -> list[dict[str, Any]]:
        try:
            recipe_and_plan = self._recipe_plan(state)
            if recipe_and_plan is None:
                return []
            _recipe, plan = recipe_and_plan
        except (TypeError, ValueError):
            return []
        expected: list[str] = []
        seen: set[str] = set()
        for row in plan["sets"]:
            for object_id in row["item_ids"]:
                if object_id not in seen:
                    expected.append(object_id)
                    seen.add(object_id)
        paths_by_object = {object_id: set() for object_id in expected}
        # Plans contain ideas, not submitted jobs. An absent or explicitly
        # cancelled job must not block delivery of the recorded ready results.
        requested = {
            str(item.payload.get('object_id') or '').strip()
            for item in session.items if isinstance(item.payload, dict)
            and getattr(getattr(item, 'status', None), 'value', None) != 'cancelled'
        }
        expected = [object_id for object_id in expected if object_id in requested]
        exported = {str(path.resolve()) for path in export_paths}
        for item in session.items:
            if not _succeeded(item) or not item.output_path or not isinstance(item.payload, dict):
                continue
            object_id = str(item.payload.get("object_id") or "").strip()
            if object_id not in paths_by_object:
                continue
            resolved = _resolved(item.output_path)
            if resolved in exported:
                paths_by_object[object_id].add(resolved)
        issues: list[dict[str, Any]] = []
        for object_id in expected:
            paths = sorted(paths_by_object[object_id])
            if not paths:
                issues.append({
                    "kind": "missing", "object_id": object_id,
                    "count": 0, "paths": [],
                })
            elif len(paths) > 1:
                issues.append({
                    "kind": "ambiguous", "object_id": object_id,
                    "count": len(paths), "paths": paths,
                })
        return issues

    def quality_reports(
        self, state: Any, session: Any, export_paths: Sequence[Path],
        requested_paths: Sequence[Path] | None = None,
    ) -> list[Any]:
        requested = {
            str(path.resolve()) for path in (requested_paths or export_paths)
        }
        opening_roles: dict[str, bool] = {}
        try:
            recipe_data = _clipart_data(state).recipe if self.collections_enabled else None
            recipe = (
                ClipartRecipe.from_dict(recipe_data)
                if isinstance(recipe_data, dict) else None
            )
            if recipe is not None:
                for obj in recipe.objects:
                    role = obj["role"]
                    text = " ".join(
                        str(obj.get(key) or "") for key in ("name", "layout")
                    ).casefold()
                    opening_roles[obj["id"]] = (
                        role == "wreath"
                        or (role == "border" and ("frame" in text or "рамк" in text))
                    )
        except (TypeError, ValueError):
            opening_roles = {}
        reports = []
        seen: set[str] = set()
        for item in session.items:
            if not _succeeded(item) or not item.output_path:
                continue
            resolved = _resolved(item.output_path)
            if not resolved or resolved not in requested or resolved in seen:
                continue
            payload = item.payload if isinstance(item.payload, dict) else {}
            result_kind = str(payload.get("result_kind") or "legacy")
            try:
                if keeps_background(result_kind):
                    continue
            except ValueError:
                result_kind = "legacy"
            object_id = str(payload.get("object_id") or "").strip()
            reports.append(studio_alpha_qc.inspect_alpha_png(
                resolved,
                residue_hint=str(payload.get("chroma_key_color") or "") or None,
                expect_interior_opening=bool(opening_roles.get(object_id, False)),
            ))
            seen.add(resolved)
        return reports
    def create_export_view(
        self, parent: Any, state: Any, paths: Sequence[Path], *,
        review_issues: Sequence[dict[str, Any]], quality_reports: Sequence[Any],
        on_membership_saved, on_fix_requested,
        workspace: Path | None = None, embedded: bool = False,
        quality_loader: Callable[[Path], Any] | None = None,
        review_paths: Sequence[Path] | None = None,
    ) -> Any | None:
        if not self.collections_enabled:
            return None
        view = SetExportDialog(
            paths, parent,
            membership=_clipart_data(state).export_membership,
            review_issues=review_issues, quality_reports=quality_reports,
            workspace=workspace, embedded=embedded,
            project_name=str(getattr(getattr(state, 'common', None), 'project_name', '') or ''),
            name_translator=_name_translator(), quality_loader=quality_loader,
            review_paths=review_paths,
        )
        view.membership_saved.connect(on_membership_saved)
        view.fix_requested.connect(on_fix_requested)
        return view

    def open_export_dialog(
        self, parent: Any, state: Any, paths: Sequence[Path], *,
        review_issues: Sequence[dict[str, Any]], quality_reports: Sequence[Any],
        on_membership_saved, on_fix_requested,
    ) -> None:
        dialog = self.create_export_view(
            parent, state, paths, review_issues=review_issues,
            quality_reports=quality_reports,
            on_membership_saved=on_membership_saved,
            on_fix_requested=on_fix_requested,
            workspace=getattr(getattr(parent, 'session', None), 'workspace_root', None),
        )
        if dialog is not None:
            dialog.exec()

    def save_membership(self, state: Any, membership: Any) -> None:
        if not self.collections_enabled:
            return
        _clipart_data(state).export_membership = validate_export_membership(membership)


__all__ = ["ClipartRunResultsExtension"]
