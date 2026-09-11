"""Offline set planning. No provider calls and no generated-image claims."""
from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any

ROLES = ("hero", "composition", "wreath", "border", "decor")
WEIGHTS = {
    "balanced": (4, 3, 2, 2, 9),
    "characters": (7, 2, 1, 1, 9),
    "decorative": (2, 3, 3, 3, 9),
}
MAX_IMAGES = 1000


def _count(value: Any, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_IMAGES:
        raise ValueError(f"Количество должно быть целым от {minimum} до {MAX_IMAGES}")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError("Описание должно быть строкой не длиннее 4000 символов")
    return value


def propose_recipes(total: int) -> dict[str, dict[str, int]]:
    """Largest-remainder allocation preserves the exact requested total."""
    _count(total, 1)
    result = {}
    for name, weights in WEIGHTS.items():
        denominator = sum(weights)
        counts = [total * weight // denominator for weight in weights]
        order = sorted(range(len(ROLES)),
                       key=lambda i: (-(total * weights[i] % denominator), i))
        for i in order[:total - sum(counts)]:
            counts[i] += 1
        result[name] = dict(zip(ROLES, counts))
    return result


@dataclass
class ClipartRecipe:
    theme: str = ""
    context: str = ""
    motifs: list[str] = field(default_factory=list)
    total: int = 20
    counts: dict[str, int] = field(default_factory=lambda: propose_recipes(20)["balanced"])
    visual: dict[str, str] = field(default_factory=dict)
    references: list[dict] = field(default_factory=list)
    objects: list[dict] = field(default_factory=list)
    assistant: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not isinstance(self.assistant, dict) or (self.assistant and set(self.assistant) != {'provider', 'model'}):
            raise ValueError('Неверные настройки текстового помощника')
        if self.assistant:
            from studio_text_models import resolve_text_model
            resolve_text_model(self.assistant['provider'], self.assistant['model'])
        from studio_clipart_references import validate_references
        validate_references(self.references)
        from studio_clipart_objects import validate_objects
        validate_objects(self.objects)
        _text(self.theme)
        _text(self.context)
        _count(self.total, 1)
        if not isinstance(self.visual, dict) or set(self.visual) - {
            "technique", "mood", "line", "material", "detail"
        }:
            raise ValueError("Неизвестные настройки визуального стиля")
        for value in self.visual.values():
            _text(value)
        if not isinstance(self.motifs, list) or len(self.motifs) > 100:
            raise ValueError("Допускается до 100 дополнительных мотивов")
        for motif in self.motifs:
            _text(motif)
        if not isinstance(self.counts, dict) or set(self.counts) != set(ROLES):
            raise ValueError("Неизвестные или отсутствующие роли набора")
        for count in self.counts.values():
            _count(count)
        if sum(self.counts.values()) != self.total:
            raise ValueError("Сумма ролей должна совпадать с числом изображений")

    def select(self, total: int, preset: str = "balanced") -> None:
        if preset not in WEIGHTS:
            raise ValueError("Неизвестный рецепт")
        counts = propose_recipes(total)[preset]
        self.total, self.counts = total, counts

    def edit_counts(self, counts: dict[str, int]) -> None:
        """Explicit edits update the visible total, without redistributing roles."""
        candidate = ClipartRecipe(self.theme, self.context, list(self.motifs),
                                  sum(counts.values()) if isinstance(counts, dict)
                                  and all(type(v) is int for v in counts.values()) else 0,
                                  dict(counts) if isinstance(counts, dict) else {})
        candidate.validate()
        self.total, self.counts = candidate.total, candidate.counts

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {"schema_version": 1, "theme": self.theme, "context": self.context,
                "motifs": list(self.motifs), "total": self.total, "counts": dict(self.counts),
                **({"visual": dict(self.visual)} if self.visual else {}),
                **({"references": deepcopy(self.references)} if self.references else {}),
                **({"objects": deepcopy(self.objects)} if self.objects else {}),
                **({"assistant": dict(self.assistant)} if self.assistant else {})}

    @classmethod
    def from_dict(cls, value: Any) -> "ClipartRecipe":
        if not isinstance(value, dict) or set(value) - {"visual", "references", "objects", "assistant"} != {
            "schema_version", "theme", "context", "motifs", "total", "counts"
        }:
            raise ValueError("Повреждённая структура рецепта")
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Неподдерживаемая версия рецепта")
        result = cls(value["theme"], value["context"], value["motifs"],
                     value["total"], value["counts"], value.get("visual", {}), value.get("references", []),
                     value.get("objects", []), value.get("assistant", {}))
        result.validate()
        result.motifs = list(result.motifs)
        result.counts = dict(result.counts)
        result.visual = dict(result.visual)
        from studio_clipart_references import validate_references
        result.references = validate_references(result.references)
        result.objects = deepcopy(result.objects)
        result.assistant = dict(result.assistant)
        return result
