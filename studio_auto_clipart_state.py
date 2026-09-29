"""Bounded module-owned draft metadata; restoring it never launches a job."""
import re


class AutoClipartStateExtension:
    def normalize_state(self, state):
        value = state.get("clipart", {}).get("automatic", {})
        if not isinstance(value, dict) or set(value) - {"compiled", "run"}:
            raise ValueError("Неверное состояние автоматического Clipart")
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
                        or set(row) - {"status", "output_path", "attempts", "editor_output_path", "stage_statuses", "source_path"}):
                    raise ValueError("Неверная запись результата")
                if not isinstance(row["status"], str) or row["status"] not in {"pending", "running", "succeeded", "failed", "cancelled"}:
                    raise ValueError("Неверный статус результата")
                if not isinstance(row["output_path"], str) or len(row["output_path"]) > 4000:
                    raise ValueError("Неверный путь результата")
                source = row.get("source_path", "")
                if not isinstance(source, str) or len(source) > 4000:
                    raise ValueError("Неверный путь исходного результата")
                edited = row.get("editor_output_path", "")
                if not isinstance(edited, str) or (edited and edited != row["output_path"]):
                    raise ValueError("Неверный путь отредактированного результата")
                stages = row.get("stage_statuses", {})
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
