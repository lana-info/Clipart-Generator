"""Bounded module-owned draft metadata; restoring it never launches a job."""
import re


class AutoClipartStateExtension:
    def normalize_state(self, state):
        value = state.get("clipart", {}).get("automatic", {})
        if not isinstance(value, dict) or set(value) - {"compiled", "run", "inactive_objects", "previous_runs", "run_settings_fingerprint"}:
            raise ValueError("Неверное состояние автоматического Clipart")
        if 'run_settings_fingerprint' in value and (
            not isinstance(value['run_settings_fingerprint'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', value['run_settings_fingerprint'])
        ):
            raise ValueError('Неверные настройки сохранённого запуска')
        if 'inactive_objects' in value:
            from studio_clipart_objects import validate_objects
            active = state.get('clipart', {}).get('recipe') or {}
            inactive = validate_objects(value['inactive_objects'])
            validate_objects(list(active.get('objects', [])) + inactive)
        if 'previous_runs' in value:
            from v3_project_state import PromptEntry
            history = value['previous_runs']
            if not isinstance(history, list) or len(history) > 100:
                raise ValueError('Неверная история запусков набора')
            for entry in history:
                if not isinstance(entry, dict) or set(entry) - {'settings_fingerprint'} != {'prompts', 'run'}:
                    raise ValueError('Неверная история запуска')
                if 'settings_fingerprint' in entry and (
                    not isinstance(entry['settings_fingerprint'], str)
                    or not re.fullmatch(r'[0-9a-f]{64}', entry['settings_fingerprint'])
                ):
                    raise ValueError('Неверные настройки предыдущего запуска')
                prompts = entry['prompts']
                if not isinstance(prompts, list) or not 1 <= len(prompts) <= 1000:
                    raise ValueError('Неверные объекты предыдущего запуска')
                for prompt in prompts:
                    normalized = PromptEntry.from_value(prompt)
                    if (normalized is None or normalized.to_dict() != prompt
                            or normalized.result_kind != 'clipart' or not normalized.object_id):
                        raise ValueError('Неверный объект предыдущего запуска')
                self.normalize_state({'clipart': {'automatic': {'run': entry['run']}}})
                if len(entry['run']) != len(prompts):
                    raise ValueError('История результатов не соответствует объектам')
        if "compiled" in value and (not isinstance(value["compiled"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["compiled"])):
            raise ValueError("Неверная версия промптов набора")
        if "run" in value:
            rows = value["run"]
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError("Неверный список результатов набора")
            for row in rows:
                if (not isinstance(row, dict)
                        or not {"status", "output_path", "attempts"} <= set(row)
                        or set(row) - {"status", "output_path", "attempts", "editor_output_path", "stage_statuses", "source_path", "cutout_path", "paid_completed_stages",
                                       "review_mark", "review_note", "versions", "review_checked", "prompt_edited"}):
                    raise ValueError("Неверная запись результата")
                from studio_clipart_versions import validate_review_row
                validate_review_row(row)
                if not isinstance(row["status"], str) or row["status"] not in {"pending", "running", "succeeded", "failed", "cancelled"}:
                    raise ValueError("Неверный статус результата")
                if not isinstance(row["output_path"], str) or len(row["output_path"]) > 4000:
                    raise ValueError("Неверный путь результата")
                source = row.get("source_path", "")
                if not isinstance(source, str) or len(source) > 4000:
                    raise ValueError("Неверный путь исходного результата")
                upscale_input = row.get("cutout_path", "")
                if not isinstance(upscale_input, str) or len(upscale_input) > 4000:
                    raise ValueError("Неверный путь изображения до апскейла")
                edited = row.get("editor_output_path", "")
                if not isinstance(edited, str) or (edited and edited != row["output_path"]):
                    raise ValueError("Неверный путь отредактированного результата")
                stages = row.get("stage_statuses", {})
                paid = row.get("paid_completed_stages", [])
                if (not isinstance(paid, list) or len(paid) > 3
                        or any(not isinstance(stage, str) or stage not in {
                            "upscale_before", "upscale_after", "background_removal"
                        } for stage in paid) or len(set(paid)) != len(paid)):
                    raise ValueError("Неверная история оплаченных этапов")
                if (not isinstance(stages, dict) or len(stages) > 32
                        or any(not isinstance(key, str) or len(key) > 80
                               or value not in ("running", "complete", "failed", "skipped", "cancelled")
                               for key, value in stages.items())):
                    raise ValueError("Неверные этапы обработки")
                if type(row["attempts"]) is not int or not 0 <= row["attempts"] <= 10000:
                    raise ValueError("Неверное число попыток")
        return state

    def before_replace(self, destination, state, *, max_bytes):
        self.normalize_state(state)
