"""Pure output filename rules shared by processing workers and UI tests."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path


_SUBJECT_LABEL = re.compile(
    r"(?:^|[\n.;])\s*(?:object|subject|объект|предмет)\s*:\s*",
    flags=re.IGNORECASE,
)
_NEXT_FIELD_LABEL = re.compile(
    r"(?:[\n.;])\s*(?:scene|details|style|palette|composition|"
    r"restrictions|technical requirements|сцена|детали|стиль|цветовая палитра|"
    r"композиция|ограничения|технические требования)\s*:\s*",
    flags=re.IGNORECASE,
)
_COMMON_SUBJECT_TRANSLATIONS = {
    "лисенок": "fox",
    "лиса": "fox",
    "лисы": "fox",
    "лису": "fox",
    "мишка тедди": "teddy bear",
    "мишка": "teddy bear",
    "медведь": "bear",
    "медвежонок": "bear cub",
    "прочерки": "dashes",
    "прочерк": "dash",
}
_CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "",
        "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
)


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    root: Path
    rough: Path
    output: Path
    transient: Path


class BatchOutputNameReservation:
    """Reserve final names before concurrent batch work starts."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self._reserved_names: set[str] = set()
        self._lock = threading.Lock()

    def _is_unavailable(self, path: Path) -> bool:
        return path.exists() or path.name.casefold() in self._reserved_names

    def _reserve(self, path: Path) -> Path:
        self._reserved_names.add(path.name.casefold())
        return path

    def reserve_processed(
        self,
        source_path: str | Path,
        *,
        overwrite: bool,
    ) -> Path:
        base = Path(source_path).stem
        destination = self.output_dir / f"{base}_ready.png"
        with self._lock:
            if overwrite and destination.name.casefold() not in self._reserved_names:
                return self._reserve(destination)
            if not self._is_unavailable(destination):
                return self._reserve(destination)
            suffix = 2
            while True:
                candidate = destination.with_name(f"{base}_ready_{suffix}.png")
                if not self._is_unavailable(candidate):
                    return self._reserve(candidate)
                suffix += 1

    def reserve_generated(self, row_index: int, prompt: str = "") -> Path:
        prompt_stem = _generated_prompt_stem(prompt)
        base = f"{prompt_stem}_{max(1, int(row_index)):02d}_ready"
        destination = self.output_dir / f"{base}.png"
        with self._lock:
            suffix = 2
            while self._is_unavailable(destination):
                destination = self.output_dir / f"{base}_{suffix}.png"
                suffix += 1
            return self._reserve(destination)


def workspace_layout(saved_path: str | Path) -> WorkspaceLayout:
    """Resolve the 3.1 workspace, migrating a legacy literal `output` path."""
    path = Path(saved_path).expanduser()
    root = path.parent if path.name.casefold() == "output" else path
    return WorkspaceLayout(
        root=root,
        rough=root / "rough",
        output=root / "output",
        transient=root / ".run",
    )


def processed_output_path(output_dir: str | Path, source_path: str | Path, run_stamp: str, *, overwrite: bool) -> Path:
    """Return a destination, preserving existing files unless overwrite is enabled."""
    base = Path(source_path).stem
    destination = Path(output_dir) / f"{base}_ready.png"
    if overwrite or not destination.exists():
        return destination
    suffix = 2
    while True:
        candidate = destination.with_name(f"{base}_ready_{suffix}.png")
        if not candidate.exists():
            return candidate
        suffix += 1


def _subject_text(prompt: str) -> str:
    """Extract the authored subject, never the structural prompt labels."""
    text = str(prompt).strip()
    match = _SUBJECT_LABEL.search(text)
    if match is None:
        return text
    value = text[match.end() :]
    next_label = _NEXT_FIELD_LABEL.search(value)
    if next_label is not None:
        value = value[: next_label.start()]
    return value.strip(" .,:;–—-\n\t")


def _translate_common_subject(subject: str) -> str:
    """Use stable English names for the common Russian clipart subjects."""
    normalized = re.sub(r"\s+", " ", subject.casefold()).strip(" .,:;–—-")
    translated = _COMMON_SUBJECT_TRANSLATIONS.get(normalized.replace("ё", "е"))
    if translated:
        return translated
    return normalized.translate(_CYRILLIC_TRANSLITERATION)


def _generated_prompt_stem(prompt: str) -> str:
    subject = _translate_common_subject(_subject_text(prompt))
    words = re.findall(r"[a-z0-9]+", subject.casefold())[:3]
    return "_".join(words)[:48].strip("_") or "clipart"


def generated_output_path(
    output_dir: str | Path,
    row_index: int,
    prompt: str = "",
) -> Path:
    prompt_stem = _generated_prompt_stem(prompt)
    base = f"{prompt_stem}_{max(1, int(row_index)):02d}_ready"
    destination = Path(output_dir) / f"{base}.png"
    suffix = 2
    while destination.exists():
        destination = Path(output_dir) / f"{base}_{suffix}.png"
        suffix += 1
    return destination
