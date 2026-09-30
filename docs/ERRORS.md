# Ошибки проекта

## processing-3.2.10-integration, 2026-09-30

First integration suite: 2059 passed, one failure in release contract after
VERSION.txt advanced to 3.2.10 while Azure appVersion default stayed 3.2.9.
Cause verified in both files and test assertion; align Azure default to 3.2.10
and recheck release tests. Existing assertions are unchanged.

Signed-module smoke harness initially omitted the image-processing capability
broker and used command install instead of declared install_workflow. Inspected
runtime/module entry contracts, corrected harness only, then verified official
signed Processing/image-processing 1.5.1: install, activation, loaded Auto UI and
engine removal PASS. Both reject Core3.2.9 due to minimum3.2.10. No application
fix needed for these diagnostic mistakes.

Windows workflow36719207715 failed before any build step. GitHub annotation
confirmed an Actions budget block; no source-code change can fix it. No installer
artifact exists from that attempt. The owner authorized temporary PUBLIC
visibility, build and return to PRIVATE. Run36723401830 from00588a2 has now
started, confirming the budget block is avoided by the authorized route.
No billing change or application fix was needed. All six signed modules1.5.1
passed installation and runtime activation against integrated Core3.2.10.
Final run36723401830 SUCCESS; helper restored PRIVATE, independently confirmed
with GitHub API. Installer source/version/hash verified and installed report
contains13 successful checks. Budget blocker resolved for this build.
Additional package UI harness initially treated auto-clipart as ProjectMode;
the contract uses CLIPART mode with a separate workflow identifier. Corrected
only the harness; all five workflow pages, Processing provider/Auto UI,
Composer local variants and shared chroma smoke then PASS.

## Подготовительное ревью Studio 3.2, 2026-09-10

1. Сохранённая контурная копия оставалась только в редакторе, тогда как ZIP
   использовал прежний session.items.output_path. Добавлена передача пары
   исходник/копия контроллеру результатов; обновляются успешный результат и
   принадлежность набору. Копии вне output допустимы только после явного
   сохранения редактором. Integration проверяет настоящий модальный редактор,
   отмену, неизменность исходника, байты PNG в ZIP/PDF-пакете, повторное открытие,
   вторую копию, сохранение проекта и отказ от постороннего исходника.
2. Общий скан credential-полей считал пути в clipart.export_membership именами
   полей. Только этот словарь теперь проверяется по схеме назначений; проверка
   настоящих полей и вложенных значений сохраняется. Integration: create/save/
   restart/load для secret-garden и Windows Users/token; неверные и секретные
   поля не перезаписывают сохранённый проект.
3. При вытеснении snapshots Undo возвращался к первоначальной alpha вместо
   предшественника первого сохранённого изменения. Сохранена подвижная база
   истории с учётом памяти, Reset отдельно использует неизменяемый исходник.
   Проверены пошаговые Undo/Redo, лимиты числа/байтов, новый edit после Undo
   и Reset. Старое утверждение теста, закреплявшее перескок, исправлено.

Все три дефекта воспроизведены до изменения реализации. Проверки и статус
нового независимого ревью находятся в STATE.md.

## processing-background-choice, 2026-09-29

Симптом: Windows 3.2.8, вкладка Обработка, результаты трёх PNG теряли рамку,
голову гуся и ботву. Диагностика подтвердила local_rembg/u2net и только этапы
background_removal/export; все три ошибочных результата отмечены succeeded.
Причина отсутствия выбора: общий редактор принудительно скрывал существующие
provider/model/colour controls. Качество сегментации U2Net не исправляется
возвратом выбора; это отдельное ограничение. Автоподбор генерационного цвета
и загрузка его provenance уже существовали, автоопределения произвольного
импортированного PNG в Processing не было.

Исправление: включаем существующие controls только для Processing. Добавлен
режим auto с определением насыщенного RGB-фона по четырём краям (90% согласия,
основной канал >=150 и превосходство >=80). При неоднозначности сохраняется
исходник и требуется ручная проверка, без нейросетевого fallback. Подтверждённая
запись цвета генерации приоритетна. Default auto только для новых Processing
настроек/рецептов; старые явные цвета сохраняются. Выпадающие поля ограничены
240/360px, текущее название полностью доступно в tooltip.

Проверки: синтетическая смешанная RGB-партия через настоящий worker, сохранение
исходников, приоритет metadata, отказ для белого/серого/тёмного/смешанного фона,
UI-to-request/preflight, project roundtrip, условная видимость и Qt-снимки.
На 72.png, 50_goose_in_garden_arch.png и 42.png определён blue. Это проверка
детектора, а не новая визуальная приёмка полного удаления. Итог прогона в STATE.md.
Белый алгоритм не реализован; Windows-сборка/платные вызовы не запускались.

## Test-environment persistence regression observed, 2026-09-29

Полный прогон обнаружил семь падений UI-проверок сохранения настроек.
Ранее на исходной 3.2.8 повторно проверен только один из семи тестов, поэтому
утверждение, что все семь проверены на исходной версии, было слишком сильным.
Диагностика подтвердила общую причину: fixtures подменяли CONFIG_FILE/ENV_FILE,
но оставляли USER_DATA_DIR настоящим. ProtectedFalCredentialStore при сохранении
пустого ключа обращался к настоящему fal_api_key.bin; read-only filesystem
возвращал EROFS и сохранение config прекращалось. Это ошибка изоляции тестов,
а не основание отключать защиту ключей.

Причина → изменение → проверка → результат: неполная изоляция пользовательских
путей → семь fixtures одновременно подменяют CONFIG_FILE и USER_DATA_DIR
через patch.multiple → все семь файлов тестов плюс тесты credential store →
49 passed, 18 subtests, 1 expected Windows DPAPI skip. Assertions и production
credential handling сохранены. Итог повторного полного прогона в STATE.md.

## processing-review-followups, 2026-09-29

Независимый reviewer на gpt-6.1-sol подтвердил два пропуска:
1. При запуске автоматически создаваемый legacy config с local_realesrgan_dir
   проходил миграцию и заменял новый Auto на blue. Processing-only default при
   отсутствующем chroma_key_color теперь auto; явно сохранённые RGB-цвета и
   обычный генерационный blue остаются прежними. Регрессия проверяет миграцию,
   отсутствие мутации config и сохранение ручных цветов.
2. refresh_from_state блокирует сигналы combobox, поэтому смена рецепта оставляла
   tooltip предыдущей модели. Подсказка явно обновляется после refresh и после
   выбора профиля. Регрессия проверяет оба перехода на настоящем Qt-редакторе.

Проверки после исправлений: 80 passed + 33 subtests; reviewer follow-up
9 passed + 4 subtests. Повторный полный прогон с исправленными fixtures:
1985 passed, zero failures; финальные review-правки отдельно проверены после
того, как текущий полный прогон уже импортировал модули. Неизвестных новых
падений нет; известный red-fur xfail и платформенные skips сохранены.
