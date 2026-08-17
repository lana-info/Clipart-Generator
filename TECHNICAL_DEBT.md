# Technical Debt

Документ только для разработчиков. Здесь нет пользовательских обещаний и
новых задач продукта.

Актуальный реестр и статусы задач находятся в [`tech_debt/README.md`](tech_debt/README.md).
Этот файл сохраняется как короткий указатель исторических архитектурных рисков.

## WorkerThread и границы V3

- Часть V3 controllers всё ещё вызывает legacy `WorkerThread` из `main.py`.
- Structured run events и legacy text progress существуют рядом.
- Нужен отдельный adapter/contract pass перед безопасным удалением legacy seam.

## Legacy и архитектура

- `main.py` остаётся большим монолитным модулем с UI, worker, provider и
  updater-кодом.
- V3 state/run/provider seams ещё не полностью отделены от V2 compatibility.
- Перед extraction требуется dependency audit и regression на трёх режимах.

## Qt lifecycle

- Полный offscreen/legacy teardown имеет отдельный native-runtime риск.
- Полный pytest проходит, но Windows может печатать diagnostic access violation
  при импорте optional `onnxruntime` для MI-GAN; это не должно маскироваться.
- Нужен отдельный process-isolated lifecycle smoke на целевых Windows окружениях.

## Installer и release pipeline

- Source/UI 3.0 не синхронизированы с упаковочными version metadata `2.0`.
- Installer и updates repository требуют отдельного release pass.
- Windows/macOS artifact, checksum, signing/notarization и clean-machine smoke
  не имеют текущего 3.0 evidence.

## Refactoring policy

- Не удалять legacy до появления owner, migration path и regression evidence.
- Не смешивать технический долг с `PRODUCT_BACKLOG.md`.
- Не исправлять debt в стабильной клиентской версии без отдельного scope,
  тестов и release decision.
