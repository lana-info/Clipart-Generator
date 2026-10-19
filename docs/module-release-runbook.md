# Official Module Releases

## Stable Studio3.2.32 Windows-only, 2026-10-19

Только Windows Core 3.2.32 (stable): release a73b51ec-9707-7cf1-f3b3-
4fb5f79dcd89, VibixImages-Setup-3.2.32.exe, size 243150812, SHA-256
b036bfe3fe77c3e86eefcda716394809125c8c73470693bbbc40655afa6f0e20. Source
d1d0cb8 (ветка codex/projects-export-hardening-20261019), run 39333551665
SUCCESS. Состав: Projects (пустые не сохраняются, лимит 20, «Продолжить» в
шапке, иконки), экспорт набора (транслитерация имён, PDF с заголовком),
мягкая кисть прозрачности и сглаженный край, аккуратное закрытие. Публикация
подтверждена владельцем; запись на сервер выполнена владельцем вручную
скриптами publish-3.2.32.sh / publish-3.2.32-finish.sh (автоматика агента
была отклонена классификатором). Штатная PostgresLicenseService-цепочка:
backup pre-studio3232-publication-20261019.dump (pg_restore list 110 PASS),
снапшот 169 → 170 релизов, дифф +1/-0/0, health ok, stored SHA совпал
(повторный хеш файла на диске). 3.2.31 остаётся published; клиенты stable
получают 3.2.32. macOS не собиралась. Evidence:
../artifacts/studio-3.2.32-stable-20261019/. Rollback: withdraw a73b51ec.

## Stable Studio3.2.31 Windows-only, 2026-10-19

Только Windows Core 3.2.31 (stable): release 2e2362fd-bd96-5928-1f9c-
cc40bfeb1a97, VibixImages-Setup-3.2.31.exe, size 243080752, SHA-256
12b4618a63722d881a08d6554f45dc7bf557573f5a68bcc76814034dbca9f316.
Source 6f508f7: EDGE_SILHOUETTE_STANDARD отделён от базового хромакей-блока;
прикрепление только в compile Auto Clipart (edge_quality), классический флоу
без стандарта — по прямому уточнению владельца. Run 39313185371 SUCCESS.
Публикация подтверждена владельцем в диалоге. Штатная PostgresLicenseService-
цепочка: backup pre-studio3231-publication-20261019.dump (18 таблиц PASS),
снапшоты 170 релизов и 47 файлов; после: health 200, discovery top1 3.2.31
(3.2.30 → 3.2.29 остались), дифф +1/-0/0, stored SHA rescan PASS. 3.2.30
остаётся published; клиенты stable получают 3.2.31. macOS не собиралась.
Evidence: ../artifacts/studio-3.2.31-stable-20261019/. Rollback: withdraw
2e2362fd.

## Stable Studio3.2.30 Windows-only, 2026-10-19## Stable Studio3.2.30 Windows-only, 2026-10-19

Опубликовано только Windows Core 3.2.30 (stable): release 821ae365-4200-
1ab1-da7c-07c9c72ab746, installer VibixImages-Setup-3.2.30.exe, size 243071600,
SHA-256 67f5e68b55f1396f94f45875d4c605c5c5c5361499b62a49541665fd8cca96e5.
Source 3b9d9ac: Fal-апскейл через хранилище Fal (5131105), единый диалог
запуска с честной стоимостью и раскрытием платной перегенерации (eb825cf,
475e632), очередь «Обновить все модули» (6c2a8bc), универсальный стандарт
силуэта в промпте (c0977f2). Run 39278189452 SUCCESS (предыдущий запуск
39276838838 отменён владельцем-агентом из-за поздней микроправки текста).
Публикация штатным PostgresLicenseService: backup
pre-studio3230-publication-20261019.dump (pg_restore list PASS), снапшоты
166 релизов и 46 файлов хранилища; после: health 200, discovery top1 3.2.30,
дифф +1/-0/0, stored SHA rescan PASS. macOS не собиралась; модули/лицензии
не тронуты. Живые платные операции и устройство владельца не проверены.
Evidence: ../artifacts/studio-3.2.30-stable-20261019/. Rollback: withdraw
821ae365.

## Stable Studio3.2.29 Windows-only, 2026-10-19## Stable Studio3.2.29 Windows-only, 2026-10-19

Опубликован только Windows Core 3.2.29 (stable, windows-x64, module_id null):
release 74dc284f-f073-a471-c5e7-2e19cf4982bc, установщик VibixImages-Setup-3.2.29.exe,
size 243086384, SHA-256 0ded202e57b10dd4b651ea6d92a239781c7197897958135914354e864703dd36.
Source 58a31a2 (fix(autoclipart): pause autosave during run confirmation);
native run 39183893974 SUCCESS (test run 39181846633 не использовался).
Публикация штатным серверным слоем PostgresLicenseService внутри контейнера
license-service-license-service-1: create_draft → attach → серверная сверка SHA/size
→ published. Без прямого SQL и без админ-сессии.

Перед публикацией: verified 0600 pg_dump
/opt/bots-stack/backups/clipart-license-service/pre-studio3229-publication-20261019.dump
(pg_restore --list PASS, 18 tables), снапшоты всех 166 релизов и SHA-список 45 файлов
хранилища. После: health 200, stable/top1 discovery 3.2.29 (дальше 3.2.28, 3.1.4),
дифф таблицы релизов +1/-0/изменено 0 — macOS 3.2.28, модули 1.5.9, лицензии
не тронуты. Stored bytes rescan SHA PASS. manifest route жив: invalid-license probe
403 UPDATE_NOT_ALLOWED.

Evidence: ../artifacts/studio-3.2.29-stable-20261019/ (stable-release-receipt.json,
server-prepublication-releases.json, server-postpublication-releases.json,
backup-verification.json, backup-pg-restore-list.txt,
prepublication-artifact-store-sha256.txt).

Ограничения: macOS 3.2.29 не собиралась (по условию). Владелец обновил приложение
на своём устройстве 2026-10-19 и подтверждает, что номер версии изменился (это
первое фактически подтверждённое owner-device обновление в истории проекта);
авторизованное скачивание по подписанному манифесту идёт через штатный клиент,
машина владельца не проверялась инструментами. 3.1.4 upgrade fixture в workflow был
skipped; пропущенные проверки не считать пройденными. Rollback: withdraw 74dc284f
(release-файл не удалять до отдельного решения владельца).

## Stable Studio3.2.22 / все модули1.5.8, 2026-10-13

По прямому поручению владельца опубликованы2Core и12module stable rows:
Windows x64 и Mac Apple Silicon. Core3.2.22, все6модулей1.5.8,
minCore3.2.22,maxExclusive3.3.0. Сначала приложение, затем «Обновления модулей».
Source1f2c45f, исправленияe4755ee. Native38344764797SUCCESS на2платформах;
Windows installed/frozen и Mac frozen/extractedCore13checksPASS. DesktopCI
38344764852:3413tests/331subtestsPASS,57SKIP/21deselected. Пакеты проверены
поSHA/version/source/ARM;6signed ZIPinspect/install/activate/runtimePASS,
несовместимыеCore3.2.21/3.3.0отвергнуты,18loopbackHTTPSPASS.

Перед публикацией сохранён проверенныйmode0600DB dump:
/opt/bots-stack/backups/clipart-license-service/
pre-studio3222-modules158-stable-publication-20261013.dump; pg_restore listPASS.
Серверные14newSHA и14previousSHA PASS; stable/latest выдача новых версий для
ordinary/beta clientsPASS. Protected release metadata и другие продукты прежние;
health200,invalid-download-token403,repositoryPRIVATE.

Удаление разрешено только для прежних выпусков, опубликованных сегодня:
на13октябряAmerica/New_York совпадений0, удалено0. Прежние3.2.21/1.5.7
остаютсяpublished, их файлы сохранены и проверены. Для rollback withdraw только
14новыхIDs изserver-stable-receipts.json, не откатывать всю business-базу.
Установленные версии приwithdraw не удаляются.

Evidence:../artifacts/studio-3.2.22-modules-stable-20261013/;
stable-release-manifest.json,server-final-live-verification.json,
same-day-deletion-audit.json иfinal-ci-verification.json. develop/3.2
интегрированаfast-forward; production sources совпадают с native source1f2c45f.
На устройстве владельца update/download и платныеAI не проверялись (0calls).
Mac ZIP ad-hoc signed без Apple notarization; legacyWindows3.1.4upgrade fixture
не задан. Эти ограничения не выдаются за пройденные проверки.

## Удаление beta Vibix после stable, 2026-10-12 (UTC)

По явному поручению владельца удалены только27beta Vibix Studio и27файлов
(1482827633bytes); TrendWatcher Video исключён по ответу владельца.
Перед удалением verified0600DB dump и private tar27members/SHA/size PASS.
Штатный delete_release:7published сначалаwithdrawn;20withdrawn удалены напрямую.
После:0undeleted beta/пустой beta discovery для Windows/MacARM/Intel;
Core3.2.21+6modules1.5.7stable discovery PASS; protectedmetadata/files SHA прежние,
включаястарыеstable иTrendWatcher beta. Licenses/grants не менялись. Health200/token403.

Штатные status=deleted tombstones остаются в DB и скрыты в admin UI.
Старыеbeta bytes теперь только в private backup вне опубликованногоartifactroot;
исторические rollback-команды ниже требуют сначала восстановить нужные файлы.
Артефакты: ../artifacts/beta-cleanup-20261012/; текущая таблица: STATE.md.

## Stable Studio3.2.21 / все модули1.5.7, 2026-10-12 (UTC)

По прямому поручению владельца14published beta rows переведены вstable
штатным PostgresLicenseService.promote_release_to_stable:2Core+6modules×2platforms
(Windows x64/Mac Apple Silicon). Версии3.2.21/1.5.7, minCore3.2.21,<3.3.0.
Менялся только channel. Подписи, bytes/SHA, IDs, status, notes и compatibility
сохранены; перепаковка, новые uploads и пересборки не выполнялись.

До операции: совпадение14identities/storedSHA, отсутствиеstable conflicts,
0600backup/pg_restore list PASS. После:14stable/latest discovery и storedSHA PASS
для обычных и beta клиентов; старыеstable/Intel/прочиеfingerprints прежние.
Ни реальные лицензии/права, ни старые файлы не менялись. Health200/token403.
Promotion contracts2PASS,1disposable-Postgres SKIP; реальная PG-операция проверена.
Артефакты: ../artifacts/studio-3.2.21-modules-stable-20261012/.
Остановить новую выдачу: withdraw14rows из promotion-receipt.json;
старыеstable остаются published. Уже установленный код при этом сохраняется.

Проверки исходного выпуска и ограничения ниже сохраняются. Mac по-прежнему
ad-hoc signed, без Apple notarization; update на устройстве владельца не проверен.
Предыдущий раздел фиксирует beta-этап до продвижения вstable.

## Beta Studio 3.2.21 / все модули 1.5.7, 2026-10-12 (UTC)

По поручению владельца опубликованы Windows x64 и одна Mac-версия, Apple Silicon.
Core3.2.21 и auto-clipart/clipart/processing/pinterest/prompt-composer/image-processing
1.5.7; совместимость Core>=3.2.21,<3.3.0. Сначала приложение, затем модульные обновления.
Новых Intel rows нет; старый Intel beta, stable и другие продукты сохранены.

Source payload db3e5c3; native CI38198534059 SUCCESS. Финальный full CI38200009717
на e8cac6a:3379tests+303subtests PASS326.30s;57SKIP,21network deselected.
Последующие исходные изменения только tests/docs, payload equivalence проверена.
Windows installation/frozenCore13/13 и Mac ARM/extractedCore13/13 PASS;
version/SHA/architecture/secret-free provenance PASS. Все6signed ZIP install/activate,
compatibility deny и actual runtime на2profiles PASS (Linux Qt offscreen).18локальных HTTPS delivery cases
PASS32.63s, включая реальное скачивание, проверку подписи и отзыв доступа.

Backup создан до stage, mode0600, pg_restore --list PASS. Опубликованы14beta rows;
прежние14target beta rows withdrawn, файлы и их SHA сохранены. Все14новых server
SHA/discovery PASS; stable/Intel/unrelated fingerprints неизменны; health200,
invalid token403, repository PRIVATE. Реальные licenses/grants не менялись.
Артефакты: ../artifacts/studio-3.2.21-modules-beta-20261011/ (вне Git).
Для rollback использовать previous-releases.json и server-retirement-receipt.json:
withdraw новые14, вернуть published старым14, не менять существующие bytes.

На устройстве владельца update/download не проверялись; paid AI calls0.
Оригинальный Windows3.1.4 upgrade не запускался без legacy fixture URL.
Mac ZIP устанавливается вручную, ad-hoc signed без Apple notarization.
Полная таблица результатов: STATE.md; причины/попытки: docs/ERRORS.md.

## Beta Studio 3.2.18 / Composer 1.5.6, 2026-10-08

Команда владельца «сделай обновление приложения». Published beta Studio3.2.18
и signed Composer1.5.6 для Windows x64, macOS arm64/x64. Core>=3.2.18,<3.3.0;
остальные пять модулей каждой платформы сохранены (Windows1.5.3, Mac1.5.5).
Изменения: подробные camera/light/composition промпты, один ввод RU/EN с авто EN,
короткие карточки вариантов, ожидание AI внизу без cost popup, единая навигация,
компактное «Продолжить работу», отсутствие пустых новостей.

Source341c526; run37872628923 SUCCESS для всех трёх платформ. Репозиторий всё
время PRIVATE. Source Composer561tests+2subtests PASS, финальные уточнения79/26
PASS; release22+4subtests, license/updater/runtime183+27subtests PASS. Native
frozen Core13/13 на каждой платформе, Mac extracted13/13. Windows installer
install/upgrade CI PASS. SHA/provenance/version/native architecture PASS.
Official signed Composer inspect/install/activate и incompatible-Core reject
PASS; actual Qt runtime для трёх целевых профилей PASS (Linux offscreen).

Backup создан и проверен pg_restore --list перед stage; published6rows,
withdrawn6 прежних Studio3.2.17/Composer1.5.5, их файлы сохранены. Active21,
storedSHA6/6, beta discovery и отсутствие в stable PASS. Stable и все прочие
release fingerprints неизменны; health200/invalidtoken403. Evidence:
../artifacts/studio-3.2.18-composer-beta-20261008/.

Сначала обновить Studio, затем Composer через «Обновления модулей».
Mac beta ad-hoc без Apple notarization, ручная установка ZIP. Реальный licensed
download/open и живой AI на устройстве владельца не проверены; платных запросов0.


## Beta Studio 3.2.17 / Composer 1.5.5, 2026-10-08

Владелец поручил commit/push, Windows/macOS build и размещение beta.
Published Studio3.2.17 для windows-x64/macos-arm64/macos-x64; отдельный signed
Composer1.5.5 для всех трёх платформ. Остальные пять Mac-модулей1.5.5, пять
Windows-модулей остаются1.5.3. Новые ZIP: Core>=3.2.17,<3.3.0, publisher-v1.
Каждый declared platform прошёл inspect/install/activation и old-Core reject;
официальный Composer ZIP прошёл click/apply/generate7 на трёх target profiles.

Windows sourcea743e50, job113129760042 SUCCESS в run37721439647; первые Mac jobs
этого run FAIL/lipo до упаковки. Mac source06b3239/run37722280070 SUCCESS для
ARM и Intel. Приложение/payload между commits одинаковы, разница только CI/test/docs.
Native frozen Core13/13 на всех платформах, Mac extracted Core13/13. ZIP CRC,
SHA/source/version и Mach-O native architecture PASS; GitHubPRIVATE подтверждён.

Server support Intel81e5003 deployed,215isolatedPGtests/Chrome6states PASS;
no migration/dependency/license change. Published16 новых rows; active21/по7.
Withdrawn только WindowsStudio3.2.16/Composer1.5.4, их файлы сохранены. Stable и
остальные пять Windows-модулей неизменны. StoredSHA16/16, beta discovery,
absence in stable, health200/invalidtoken403 PASS; verified backup перед stage.

Mac beta ad-hoc signed без Apple notarization. Updater скачивает ZIP и открывает
Finder, установка вручную. Реальное обновление/licensed download/open на
устройстве владельца не проверены; liveKIE тоже не проверен, ключ только на ПК.
Не читать и не переносить credential store. Сначала Studio, затем Composer.
Evidence: ../artifacts/studio-3.2.17-composer-beta-20261008/.
Не заменять существующие bytes под выпущенной версией; для правок новая версия.

## Beta Studio3.2.13 и Composer1.5.4, 2026-10-06

Владелец разрешил commit/push и выпуск после просмотра результатов. Build source
7d7bcde2fc2cbaa2be7fd138bd04163a9c140abb; Windowsrun37546983128SUCCESS.
PUBLIC→build→PRIVATE выполнено, итогPRIVATE проверен отдельно. Installer SHA/version/
provenance совпали; установленный frozenCore13/13checks PASS, в том числе contour.
Studio исправляет высоту списка файлов при выборе пера. Composer1.5.4 исправляет
падение при выборе варианта и3ошибки потери текста; это отдельное обновление модуля.

Пакет1.5.4: windows-x64,Core>=3.2.12,<3.3.0, pinnedpublisher signature и все6files
побайтно соответствуют build source. Independent temporary install/runtime PASS,
Core3.2.11/3.3.0 reject. Остальные5модулей остаются опубликованными1.5.3.
Новые2релиза published beta; предшественники Studio3.2.12/Composer1.5.3 withdrawn,
старые файлы сохранены. Stable и остальные релизы неизменны. Live storedSHA2/2PASS,
health200/invalidtoken403. Перед публикацией создана и проверена backup базы.

Evidence: ../artifacts/studio-3.2.13-composer-beta-20261006/.
Реальное обновление устройства владельца и licensed download/open ещё не проверены.
Не заменять байты версий1.5.3/1.5.4/3.2.12/3.2.13: для будущих правок новая версия.

## Chroma material candidate, 2026-10-05

Studio source version and Azure default now3.2.12. Local unpublished signed module1.5.3 candidates: auto-clipart, clipart, processing and image-processing, minCore3.2.12 and windows-x64. Existing module/version bytes are not overwritten or published. Local Ed25519 inspect/install verifies4/4; previous Core3.2.11 rejects4/4. Source evidence and actual/approved UI: STATE.md current task and docs/ui/3.2/chroma-material-mode-20261005/README.md. Artifacts: ../artifacts/chroma-material-beta-3.2.12-modules-1.5.3-20261005/release-set.json.

Core API1 remains backward compatible with old opaque-only components. Material mode requires a component explicitly advertising legacy; worker construction rejects unsupported mode before any generation starts. The new component factory uses a Core field absent from3.2.11, so do not relax studio_min. New automatic/ordinary workflow code also depends on the new Core settings/registry. The processing candidate retains the previously reviewed white-readiness Core dependency. No new Pinterest/prompt-composer packages are required for this feature.

Owner authorized commit/push/build and temporary PUBLIC→PRIVATE on2026-10-06. Source438a665, Windowsrun37490182834SUCCESS; repositoryPRIVATE verified, installer/source/version/SHA exact. Installed frozen Core13checks and local-processing smoke PASS. Beta kit: ../artifacts/studio-3.2.12-chroma-beta-20261006/. All4 module payloads independently match committed source. Catalog/upload/publication, licensed new-module download/run, owner-device upgrade and full3-settings Windows acceptance remain pending. Keep prior beta available until acceptance. Do not deploy production while fulfilling beta acceptance.


## Next reviewed candidate, 2026-10-01

The source candidate is ready for a separately authorized Studio3.2.12 build.
Use an explicit AppVersion3.2.12; source VERSION/Azure default have not been
changed in this preparation phase. Prepare new processing and image-processing
artifacts as version1.5.3 with minimumCore3.2.12; the processing payload now
imports shared white-background readiness APIs from that Core. Unchanged1.5.2
modules may stay published. Never replace existing release bytes under the same
version. No new official packages/build/deployment/publication have been run.
Installed Windows licensed delivery and old-version upgrade remain unverified.
Keep Studio3.2.10/modules1.5.1 beta available until new Windows acceptance.

## Trust And Custody

Studio pins `vibix-publisher-v1` in `studio_module_delivery.py`. Only the public
Ed25519 key is committed. Packages cannot add trust keys. License and release
metadata signing remain separate from package signing.

The publisher key was provisioned on 2026-09-19 at
`/root/.local/share/vibix-studio-signing/publisher-v1.pem`, outside all checkouts,
with directory mode 0700 and file mode 0600. Never print, attach, commit or copy
the private key into a build artifact, `.env`, or desktop installation.
There is currently no verified off-host backup. Before production publication,
the operator must arrange secure recovery custody; loss requires a shell release
pinning a new public key. Key rotation/revocation likewise requires a controlled
shell update, not an unsigned server setting.

`studio_module_release.py init-key --key-file <protected-path>` is a one-time
operator command. It refuses to overwrite a key or create one in this checkout,
and prints only its public half. A new public key must be reviewed and pinned in
the shell before `prepare` accepts its private key.

## Preparation

Run from the reviewed Studio checkout with its existing Python environment:

```bash
python studio_module_release.py prepare \
  --key-file /root/.local/share/vibix-studio-signing/publisher-v1.pem \
  --key-id vibix-publisher-v1 \
  --output /absolute/path/to/new-release-directory \
  --version 1.1.0 --studio-min 3.2.1 --studio-max-exclusive 3.3.0 \
  --platform windows-x64 --platform macos-x64
```

This prepares four workflows (including `auto-clipart`) and the shared
`image-processing` component from explicit inventories, signs each
package, and verifies it with the desktop installer for every declared platform.
It outputs ZIPs and `release-set.json` with SHA-256/size/compatibility. It never
imports payload code, runs providers, sweeps user directories or overwrites an
existing release directory. A filesystem failure may leave an incomplete new
directory; do not publish it without successful verification.

The 2026-09-19 candidate artifacts are in
`/root/projects/Clipart Generator/artifacts/official-modules-1.0.0-20260919`.
These are independently signed workflow packages, not desktop installers.
Those historical artifacts contain only the three legacy workflows. The legacy
generation module is `clipart`; automatic collections use `auto-clipart` and must
be packaged from the new source checkpoint. Its payload includes the automatic
controller and a package-local copy of the reused generation controller, so an
ordinary generator update cannot silently replace that base. The eight-step Core
shell, state adapter and export services remain dependencies of the shell.
New packages also own planning/prompt dependencies listed below.
Do not offer this package to the historical 3.2.0 test installer: it lacks that
Core composition. The current test packages use minimum Studio 3.2.1, keeping
older installers on their compatible legacy module releases. A new installed
acceptance build is required before production publication of automatic Clipart.

## Draft Upload

After the module-aware service and migration 012 pass staging acceptance:

```bash
python studio_module_release.py upload-draft /absolute/path/processing-1.0.0.zip \
  --service-url https://services.etsyneuroclub.com/licenses \
  --platform windows-x64 --studio-version 3.2.0
```

The command requires an interactive terminal and prompts privately for admin
password and TOTP; it refuses the echoed-password fallback. Credentials are never
command arguments or saved sessions. HTTPS certificate validation remains enabled;
redirects are refused. Signature, platform, compatibility and package structure
are rechecked before any draft is created. Metadata is extracted from the signed
package, and the exact inspected bytes are uploaded and compared with the server's
hash and size. Repeat explicitly for each module/platform to be released.

No automatic retry or publication occurs. A failure can leave a draft; the command
prints its ID immediately after creation. Inspect that draft in the panel before
retrying. A successful upload remains invisible to desktop manifests until the
administrator publishes it. Use the panel to publish or withdraw releases.

## Acceptance And Recovery

- Test service migration 012 on a disposable database first; production rollout
  must preserve the active deployment override in the service runbook.
- Verify an installed shell trusts the publisher and opens all four workflows;
  check download progress, interruption, bad signature and denied/revoked rights.
- Check existing projects and the separate video product registration unchanged.
- Test Windows installer/update and native UI on Windows; offscreen Linux Qt
  tests do not establish installed Windows acceptance.
- Withdraw published module rows before rolling a server back to code without
  module-aware manifest filtering. Otherwise the old server can advertise ZIPs
  as application updates. Withdrawing a release does not uninstall active code.
- A known installed prior module can be restored via the verified runtime
  rollback API when no workflow owns an active lease. There is no user-facing
  rollback control in the current update dialog.

No production artifacts or customer releases were published during preparation.

## Shared processing bridge and independent news (2026-09-23)

The compatible service is deployed on 2026-09-23 with migrations012/013;
Studio Test3.2.4 has passed its Windows installer checks. Ordinary Studio3.2.4 also passed its installed Windows checks;
verified build delivery is tracked in STATE.md. New packages require minimum Studio3.2.4. The older service does not derive shared-component download
rights from workflow entitlements. Historical Studio3.2.1 packages do not imply
that the installed shell supports this new API: choose a new approved bridge
release version and set all new packages' studio-min accordingly. Do not publish
using the older example version bounds above without that compatibility check.

The component contains `studio_processing_engine.py`, `chroma_key.py`,
`chroma_rim.py` and `chroma_profile.py`. Shell-owned `studio_processing_api.py`
defines API1 and result validation; worker dispatch, credentials and receipts stay
in Studio. The selected engine reports its actual profile to receipts. Built-in
v9 remains available before first component installation. Once selected, an
invalid component produces an error instead of silently using another algorithm.

Automatic Clipart includes its builder/planning UI, text client, planner, object
compiler, commercial/style/holiday guidance and prompt generator/schema. Ordinary
Generation owns its generator/schema. Packaging rewrites inventory-local imports
and eagerly loads helpers within the runtime callback to avoid later bytecode
writes in immutable verified package directories.

The Updates dialog still has four workflow rows. A consumer check discovers both
its workflow release and the shared processing release. The existing Update button
stages both and atomically activates them, or updates only the engine if that is
the sole available change. Active engine jobs or live updated workflow pages block
activation. Failure restores previous pointers and loaded code. A live entitlement
for any consumer allows component download; it never unlocks another workflow.

To prepare only an algorithm update, use the existing single-package tool after
explicit artifact/release authorization (placeholders require approved values):

```bash
python studio_module_packaging.py --module image-processing \
  --version <component-version> --studio-min <bridge-version> \
  --studio-max-exclusive <incompatible-version> \
  --platform windows-x64 --platform macos-x64 \
  --key-id vibix-publisher-v1 --signing-key-file <protected-key-path> \
  --output <new-absolute-zip-path>
```

Upload the verified ZIP using `studio_module_release.py upload-draft`, then review
and publish that component revision only. Workflow package versions need not
change for a compatible algorithm update. Compatibility-breaking API changes
still require a coordinated Studio release. Never store the private key in Git.

News needs no ZIP or application version bump after this bridge is installed.
In admin choose «Новости Studio», enter a title and body, save a draft or publish.
To edit published text, withdraw it first. The latest published announcement is
shown; withdrawing it may reveal an older still-published announcement. Withdraw
all to clear the home feed. Text is plain (100/600 characters), without executable
HTML. Publication date is server-generated. Studio refreshes at startup/every10min
and keeps its last received announcement offline. Changes reach offline users
when they next connect. A valid license/device is required; an expired update
entitlement does not prevent reading news.

Source verification: full PostgreSQL service suite, signed local HTTPS delivery,
component-only updates, grouped rollback, rights/revocation, worker leases,
package-local prompt execution, and Chrome/offscreen news scenarios. See STATE.md
for counts and `docs/ui/3.1/independent-components-news/` for approved/actual views.
Installed Windows, final signed production artifacts and deployment are separate
acceptance steps and were not executed by these source checks.


## Резервная копия ключа: действия владельца

Рекомендуемое хранение: зашифрованный файл на личном компьютере и его вторая
копия на отдельной флешке. Пароль хранить в менеджере паролей, отдельно от файла.
Обычная копия на том же сервере не защищает от потери сервера. Приватный ключ и
пароль не отправлять в чат, GitHub, новости или публичные ссылки.

1. Открыть собственный SSH-терминал сервера. Создать уникальный длинный пароль
   в менеджере паролей. Следующая команда спросит его дважды скрытым вводом.
   Рабочий ключ не изменяется; создаётся только зашифрованная копия:

   ```bash
   umask 077
   set -o noclobber
   openssl pkcs8 -topk8 -v2 aes-256-cbc -iter 600000 \
     -in /root/.local/share/vibix-studio-signing/publisher-v1.pem \
     > /root/.local/share/vibix-studio-signing/publisher-v1-backup-20260923.encrypted.pem
   ```

   Если файл уже существует, остановиться и проверить его; не перезаписывать.
   Не добавлять пароль в аргументы команды. Формат и скрытый запрос пароля:
   [официальная документация OpenSSL](https://docs.openssl.org/3.0/man1/openssl-pkcs8/).

2. Проверить расшифровку без вывода приватного ключа. Первая команда запросит
   пароль резервной копии. Обе команды выводят только SHA-256 публичного ключа;
   строки должны совпадать с публичным отпечатком `publisher-v1`:
   `0688e67e256e3f2365339fb498a734e92150bc1523b26e8e5faf2de3f59ed583`.
   При любой ошибке OpenSSL проверка не пройдена:

   ```bash
   set -o pipefail
   openssl pkey -in /root/.local/share/vibix-studio-signing/publisher-v1-backup-20260923.encrypted.pem -pubout -outform DER | sha256sum
   openssl pkey -in /root/.local/share/vibix-studio-signing/publisher-v1.pem -pubout -outform DER | sha256sum
   sha256sum /root/.local/share/vibix-studio-signing/publisher-v1-backup-20260923.encrypted.pem
   ```

3. В своём SFTP-клиенте скачать **только** файл
   `publisher-v1-backup-20260923.encrypted.pem` на компьютер. Подключение то же,
   которым владелец пользуется для SSH. Если подключения ещё нет, сначала
   настроить его; не публиковать файл через сайт ради скачивания.

4. В PowerShell на компьютере проверить скачанный файл (подставить его путь):

   ```powershell
   Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\путь\publisher-v1-backup-20260923.encrypted.pem'
   ```

   SHA-256 должен совпасть с последней серверной командой. Скопировать файл на
   флешку и проверить её копию той же командой. Не хранить пароль рядом с копиями.

5. Записать в менеджере паролей: «Vibix publisher-v1», пароль, расположение обеих
   копий, дату и публичный отпечаток. Сообщить исполнителю только факт успешного
   сохранения и проверки, без пароля и содержимого ключа. До этого внешний backup
   остаётся неподтверждённым и публикация модулей не завершена.

Команды шифрования и сравнения проверены на одноразовом тестовом Ed25519-ключе.
Это проверка процедуры, а не подтверждение наличия копии рабочего ключа у владельца.


## Verified ordinary Studio3.2.5, 2026-09-23

Windows build35899489246, artifact10769240994, source17095eb passed original3.1.4
upgrade, installed Bezier edit/save and local inference checks. Ordinary installer
is published on the working server; SHA256:
`246e1a3fca90b5131e3cf6e488f9230cd6dc45c267aa08daa541519da77537c2`.
Native data checks use five synthetic files; real customer activation/projects
were not exercised. No user credentials were used.

Five official packages1.4.0 (all four workflows plus image-processing) require
Studio>=3.2.5,<3.3.0 on Windows x64. Signature/install/runtime activation verified;
all three processing consumers acquired packagedv9 and passed an image fixture.
These five rows are DRAFTS in working admin, pending off-host publisher-key backup.
The ordinary installer already includes the current built-in implementation.
No publisher-key backup on the owner's computer/USB has yet been confirmed.

## On-demand shell candidate 3.2.9 (2026-09-29)

The shell catalog now has five downloadable tools. `prompt-composer` is a
separate signed payload with a Core host for credentials, storage and paid-request
confirmation. Prepare this release set with minimum Studio **3.2.9**, maximum
exclusive **3.3.0**, Windows only until native acceptance on another platform.
The proposed module set version is **1.5.0**; it includes the five tools and the
shared `image-processing` dependency. Never publish the Composer package with a
lower minimum: older shells lack its Core bridge.

Production was audited read-only at service checkpoint beta-modules-53b42ef:
four tools have active Windows packages, and Club/VIP grants those four exact
IDs. Composer has no published package or customer grants. The existing server
API accepts its ID, proven using the unchanged server with an ephemeral HTTPS
fixture. Server code, deployment, bundles and customer assignments were not
changed. Preparing ZIPs does not publish or grant access. Catalog management of
Composer is a separate administrative step; do not infer its right from a bundle
name or silently add it to existing customers.

Fresh installs contain the Core shell and shared services. No workflow entry
controller or Composer payload is shipped as a fallback. Existing user projects,
credentials and module pointers retain their storage locations. An old project
whose module is missing stays saved until its licensed module is installed.
Installed damaged packages fail closed; automatic replacement of a damaged
version under the same version number is not implemented. Release a new signed
version or perform a separately authorized support recovery.

Native Windows acceptance of the shell and downloaded packages is required before
production publication. Source tests and preparation/signature inspection alone
are not installed Windows acceptance.
