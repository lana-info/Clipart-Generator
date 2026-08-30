# Vibix Images 3.0

Desktop-приложение для трёх рабочих сценариев:

- Clipart — подготовка и запуск генерации изображений;
- Pinterest — подготовка вариантов и запуск Pinterest-изображений;
- Processing — локальная обработка готовых изображений.

## Статус релиза

Source-build и Windows packaging используют `release/VERSION.txt` как
единственный source of truth. Публикация обновлений остаётся отдельным
согласованным шагом; draft-артефакты не считаются опубликованным релизом.

## Для пользователя

- [USER_GUIDE.ru.md](USER_GUIDE.ru.md) — полное иллюстрированное руководство: API-ключи, промпты, CSV, Clipart, chroma key, прозрачность, Pinterest и Processing;
- [USER_INSTALL_GUIDE.md](USER_INSTALL_GUIDE.md) — установка и первый запуск;
- [API_KEYS_GUIDE.ru.md](API_KEYS_GUIDE.ru.md) — регистрация и получение ключей KIE.AI, fal.ai и PhotoRoom;
- [MANUAL_SMOKE_TEST_3.0.md](MANUAL_SMOKE_TEST_3.0.md) — пользовательская проверка;
- [KNOWN_LIMITATIONS_3.0.md](KNOWN_LIMITATIONS_3.0.md) — ограничения и ручные проверки;
- [RELEASE_NOTES_3.0.md](RELEASE_NOTES_3.0.md) — изменения версии 3.0.

## Быстрый старт из исходников

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Для локального тестирования используйте копии изображений и отдельную папку
результатов. Реальные платные запросы к KIE, PhotoRoom, RunPod и другим
провайдерам без явного разрешения не выполняются.

## Сборка руководства

Скриншоты и документы собираются локально без API-запросов:

```powershell
python scripts/capture_user_guide_screenshots.py
python scripts/generate_user_guide_documents.py
```

Готовые файлы появятся в `output/pdf/Vibix_Images_User_Guide.ru.pdf` и
`output/doc/Vibix_Images_User_Guide.ru.docx`. Каталог `output` не хранится в
Git, поэтому для передачи документов используйте именно эти локальные файлы.
Для PDF нужен Chrome, Chromium или Edge. Если браузер не найден автоматически,
укажите его явно, например:

```powershell
python scripts/generate_user_guide_documents.py --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

## Проверки

```powershell
python -m pytest -q
python -m py_compile main.py v3_run_queue.py
git diff --check
```

## Документы проекта

- [PRD_3.0.ru.md](PRD_3.0.ru.md) — требования;
- [TASKS_3.0.ru.md](TASKS_3.0.ru.md) — задачи и evidence;
- [UI_WIZARD_3.0.ru.md](UI_WIZARD_3.0.ru.md) — UX-контракт wizard;
- [QUALITY_GATE_ISSUES_3.0.md](QUALITY_GATE_ISSUES_3.0.md) — quality gate;
- [REAL_USE_TEST_3.0.md](REAL_USE_TEST_3.0.md) — эксплуатационная проверка;
- [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md) — будущие идеи, не roadmap;
- [TECHNICAL_DEBT.md](TECHNICAL_DEBT.md) — указатель технического долга;
- [DOCUMENTATION_AUDIT_3.0.md](DOCUMENTATION_AUDIT_3.0.md) — аудит структуры документов.

## Ветки и контрольные точки

- `develop/3.0` — текущая подготовка source-релиза;
- `release/3.x` — стабильная контрольная ветка;
- `v3.0.0-rc1` — неизменяемая контрольная точка.
