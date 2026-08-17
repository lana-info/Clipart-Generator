# P0 — dependency, binary и build provenance

Status: Done (2026-08-17)

Evidence: `constraints-build.txt`, `build_provenance.py`,
`tests/test_build_provenance.py` and the Windows workflow hash gate for the
official Real-ESRGAN archive (`1bbbdb12…ce3fa9a`). The build now fails closed
before extraction on archive mismatch and emits secret-free machine-readable
provenance. Dependency lock coverage is for the production Windows build; dev
tools remain separately managed.

## Проблема и evidence

- `requirements.txt` содержит диапазоны версий без lock/constraints и hash
  provenance; CI устанавливает текущие пакеты на момент запуска.
- Workflow скачивает Real-ESRGAN по URL и распаковывает его без проверки
  SHA-256/подписи до включения в installer.
- PyInstaller/Inno Setup и Python version частично заданы в workflow, но нет
  единого build manifest с версиями, source URL, hashes и license inventory.

## Минимальная реализация

1. Зафиксировать constraints/lock для production build и отдельно dev tools;
   не обязательно сразу переходить на новый package manager.
2. Добавить SHA-256 (или официальную signature verification) для внешнего
   Real-ESRGAN archive и fail-closed при mismatch.
3. Сформировать machine-readable build provenance: Python, PyInstaller,
   Inno Setup, dependencies, bundled binaries/models, licenses.
4. Проверить, что provenance не содержит secrets и попадает в artifact metadata,
   а не в пользовательский runtime.

## Acceptance

- Повторный build из того же commit использует те же разрешённые dependency/binary
  revisions или явно фиксирует controlled update.
- Изменение hash внешнего бинарника останавливает build до упаковки.
- SBOM/license inventory покрывает `third_party`, rembg/onnxruntime/OpenCV,
  Real-ESRGAN и packaging tools.

## Не делать сейчас

Не вводить тяжёлую supply-chain платформу или автоматическую публикацию; нужен
проверяемый constraints + hash gate.
