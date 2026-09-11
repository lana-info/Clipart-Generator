"""Explicit output intent; never infer a destructive operation from prompt words."""

RESULT_KINDS = frozenset({"legacy", "clipart", "pattern", "background", "texture", "journal_page"})
SURFACE_KINDS = frozenset({"pattern", "background", "texture", "journal_page"})


def validate_result_kind(value):
    if not isinstance(value, str) or value not in RESULT_KINDS:
        raise ValueError("Неизвестный тип результата; автоматическая обработка остановлена")
    return value


def keeps_background(value):
    return validate_result_kind(value) in SURFACE_KINDS
