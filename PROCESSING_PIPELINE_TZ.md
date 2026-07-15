# ТЗ: локальный апскейл, удаление фона и удаление контура

## 1. Цель

Добавить в Clipart Generator гибкий пайплайн массовой постобработки клипартов:

1. опциональное локальное удаление небольшой видимой метки;
2. опциональный апскейл до удаления фона;
3. опциональный Unsharp Mask;
4. удаление фона;
5. опциональный апскейл после удаления фона;
6. удаление белого/грязного контура по краю объекта;
7. trim пустых краев;
8. сохранение готового PNG.

Главная цель - получить качественные PNG-клипарты для Etsy/маркетплейсов дешевле, стабильнее и с большим контролем, чем при полностью облачной обработке.

## 2. Текущий контекст проекта

- Основной код: `main.py`.
- GUI: PyQt6.
- Уже есть KIE-обработка:
  - `topaz/upscale`;
  - `recraft/crisp-upscale`;
  - `recraft/remove-background`.
- Уже есть trim:
  - прозрачные края;
  - белые края;
  - черные края;
  - trim всегда выполняется в конце.
- В `requirements.txt` уже есть:
  - `Pillow`;
  - `rembg`;
  - `onnxruntime`;
  - `opencv-python`;
  - `numpy`.
- Добавлен локальный Real-ESRGAN:
  - `realesrgan-ncnn-vulkan-20211212-windows/realesrgan-ncnn-vulkan.exe`;
  - модели в `realesrgan-ncnn-vulkan-20211212-windows/models`;
  - приложение поддерживает проверенные scale `2x` и `4x`.

## 3. Основное решение

Первая версия должна поддерживать 2 независимых провайдера:

### 3.1. Апскейл

Провайдеры:

- `KIE`: текущий облачный режим.
- `Local Real-ESRGAN`: локальный запуск `realesrgan-ncnn-vulkan.exe`.

Real-ESRGAN профили:

- `photo` -> модель `realesrgan-x4plus`;
- `clipart` -> модель `realesrgan-x4plus-anime`.

Scale:

- `2x`;
- `4x`.

Default для клипартов:

- provider: `Local Real-ESRGAN`;
- profile: `clipart`;
- scale: `4x`, если скорость приемлема, иначе `2x`.

### 3.2. Удаление фона

Провайдеры:

- `KIE`: текущий `recraft/remove-background`;
- `PhotoRoom Standard`: `POST https://sdk.photoroom.com/v1/segment`, PNG/RGBA, `size=full`;
- `Local rembg`: локальная обработка через Python-библиотеку `rembg`.

Local rembg профили:

- `clipart` -> `birefnet-general`;
- `people` -> `birefnet-portrait`;
- `anime` -> `isnet-anime`;
- `fallback` -> `isnet-general-use`.

Default:

- `Local rembg` + `birefnet-general`.

KIE остается fallback, если локальная модель дает плохой результат или слишком медленная.

### 3.3. Удаление контура

Добавить отдельную настройку, независимую от trim:

- включить/выключить;
- сила: `1 px`, `2 px`, `3 px`.

Назначение:

- убрать белую кайму;
- убрать грязные полупрозрачные пиксели;
- "съесть" край alpha-маски внутрь объекта.

Технически:

- работать с alpha-каналом;
- сначала обнулить почти прозрачные пиксели;
- затем применить эрозию alpha-маски через `ImageFilter.MinFilter(size=3)` столько раз, сколько выбрано пикселей;
- сохранить RGB как есть, менять только alpha.

Важно:

- это не trim;
- trim обрезает пустое поле вокруг объекта;
- удаление контура меняет край самого объекта.

## 4. Рекомендуемый порядок пайплайна

Для большинства клипартов:

1. Исходник.
2. Опциональное локальное удаление небольшой видимой метки.
3. Опциональный апскейл до удаления фона.
4. Опциональный Unsharp Mask.
5. Удаление фона.
6. Опциональный апскейл после удаления фона.
7. Удаление контура 1-3 px.
8. Trim пустых краев.
9. Сохранение PNG.

Почему апскейл до удаления фона:

- Real-ESRGAN стабильнее работает с обычным RGB-изображением;
- прозрачные PNG могут дать артефакты;
- после удаления фона край можно дополнительно подчистить.

Исключение:

- если исходник уже прозрачный PNG, можно пропустить удаление фона и применить только contour shrink + trim.

## 5. Настройки config

Добавить новые ключи:

```json
{
  "upscale_provider": "kie",
  "upscale_after": false,
  "upscale_after_provider": "local_realesrgan",
  "local_realesrgan_dir": "D:\\WorkOS\\Clipart Generator\\realesrgan-ncnn-vulkan-20211212-windows",
  "local_realesrgan_profile": "clipart",
  "local_realesrgan_scale": 4,
  "local_realesrgan_after_scale": 4,
  "kie_upscale_after_model": "topaz/upscale",
  "remove_bg_provider": "kie",
  "photoroom_api_key": "",
  "local_rembg_profile": "clipart",
  "local_rembg_model": "birefnet-general",
  "edge_shrink_enabled": false,
  "edge_shrink_pixels": 1
}
```

Совместимость:

- старые ключи `upscale`, `remove_bg`, `trim_enabled`, `trim_mode`, `trim_position`, `kie_upscale_model`, `kie_remove_bg_model` сохранить;
- если новых ключей нет, приложение должно работать по старому поведению.

## 6. Изменения в UI

### 6.1. Блок обработки

Оставить текущие чекбоксы:

- Апскейл до удаления фона;
- Апскейл после удаления фона;
- Удаление фона;
- Trim;
- Экспорт 300 DPI.

Добавить:

- чекбокс `Удалять контур`;
- выбор силы: `1 px`, `2 px`, `3 px`.

### 6.2. Блок настроек апскейла

Добавить выбор провайдера:

- `KIE`;
- `Local Real-ESRGAN`.

Если выбран KIE:

- показывать текущий выбор KIE-модели.

Если выбран Local Real-ESRGAN:

- показывать путь к папке Real-ESRGAN;
- профиль `Photo / Clipart`;
- scale `2x / 3x / 4x`.

### 6.3. Блок настроек удаления фона

Добавить выбор провайдера:

- `KIE`;
- `PhotoRoom Standard`;
- `Local rembg`.

Если выбран KIE:

- показывать текущий `recraft/remove-background`.

Если выбран PhotoRoom Standard:

- использовать отдельный скрытый `PhotoRoom API Key` из настроек;
- запрашивать `format=png`, `channels=rgba`, `size=full`, без crop и despill;
- не требовать KIE API Key для process-only.

Если выбран Local rembg:

- показывать профиль:
  - `Clipart`;
  - `People`;
  - `Anime`;
  - `Fallback`.

## 7. Техническая реализация

### 7.1. Общий pipeline

Текущий `_run_kie_processing_pipeline` завязан на URL и KIE.

Нужно сделать общий локально-облачный pipeline:

- этап получает локальный путь или URL;
- если следующий этап требует KIE, локальный файл загружается в KIE;
- если следующий этап локальный, URL сначала скачивается в `raw/`;
- каждый этап сохраняет промежуточный файл в `raw/`.

Минимальный безопасный вариант:

- не переписывать все сразу;
- добавить локальные ветки в существующие места;
- сохранить старое поведение KIE без изменений.

### 7.2. Local Real-ESRGAN

Добавить функцию:

```text
run_local_realesrgan(input_path, output_path, profile, scale)
```

Команда:

```powershell
realesrgan-ncnn-vulkan.exe -i input.png -o output.png -n realesrgan-x4plus-anime -s 4
```

Маппинг:

- `photo` -> `realesrgan-x4plus`;
- `clipart` -> `realesrgan-x4plus-anime`.

Проверки:

- путь существует;
- `realesrgan-ncnn-vulkan.exe` существует;
- папка `models` существует;
- scale только `2`, `3`, `4`;
- subprocess завершился с кодом `0`;
- output-файл реально создан.

### 7.3. Local rembg

Добавить функцию:

```text
run_local_rembg(input_path, output_path, profile/model)
```

Требования:

- использовать `new_session(model_name)`;
- сессию переиспользовать на batch, а не создавать на каждый файл;
- сохранять результат как PNG с alpha.

Маппинг профилей:

- `clipart` -> `birefnet-general`;
- `people` -> `birefnet-portrait`;
- `anime` -> `isnet-anime`;
- `fallback` -> `isnet-general-use`.

Если модель не скачана:

- rembg может скачать ее при первом запуске;
- в UI/log показать, что первый запуск может быть долгим.

### 7.4. Удаление контура

Добавить функцию:

```text
shrink_alpha_edges(input_path, output_path, pixels)
```

Правила:

- `pixels <= 0` -> просто сохранить без изменения;
- `pixels` ограничить диапазоном `1..3`;
- применять только к RGBA;
- если alpha отсутствует, конвертировать в RGBA, но предупредить в log, что явной прозрачности не было;
- менять только alpha-канал.

Псевдологика:

```text
open image as RGBA
split r,g,b,a
a = alpha threshold cleanup
repeat pixels times:
    a = MinFilter(size=3)
merge r,g,b,a
save PNG
```

## 8. Валидация

Минимальные проверки:

1. `python -m py_compile .\main.py`
2. Сценарий KIE-only:
   - KIE upscale;
   - KIE remove background;
   - trim.
3. Сценарий local-only:
   - Local Real-ESRGAN;
   - Local rembg;
   - edge shrink 1 px;
   - trim.
4. Сценарий смешанный:
   - Local Real-ESRGAN;
   - KIE remove background;
   - edge shrink 2 px.
5. Сценарий уже прозрачного PNG:
   - без remove background;
   - edge shrink 1 px;
   - trim.

Что проверить глазами:

- нет белой каймы на темном фоне;
- не съедены важные тонкие детали;
- PNG действительно прозрачный;
- итоговый размер соответствует выбранному scale;
- приложение не требует KIE API Key, если выбран полностью локальный pipeline.

## 9. Риски

### 9.1. Real-ESRGAN медленный

Решение:

- scale `2x` как быстрый режим;
- scale `4x` как качественный режим;
- показывать в UI, что локальный апскейл может быть медленным.

### 9.2. rembg впервые скачивает модели

Решение:

- добавить понятное сообщение в log;
- не считать первый долгий запуск ошибкой.

### 9.3. Слишком сильное удаление контура

Решение:

- default `1 px`;
- `2-3 px` только вручную;
- дать возможность полностью выключить.

### 9.4. Большие бинарники Real-ESRGAN

Решение:

- не коммитить папку `realesrgan-ncnn-vulkan-20211212-windows`;
- добавить ее в `.gitignore`;
- хранить путь в config.

## 10. Задачи реализации

### Этап 1. Подготовка

[ ] Добавить `realesrgan-ncnn-vulkan-20211212-windows/` в `.gitignore`.

[ ] Добавить новые default config keys в `main.py`.

[ ] Проверить, что старые config-файлы открываются без ошибок.

### Этап 2. UI

[ ] Добавить выбор провайдера апскейла: `KIE` / `Local Real-ESRGAN`.

[ ] Добавить настройки Local Real-ESRGAN: путь, профиль, scale.

[ ] Добавить выбор провайдера удаления фона: `KIE` / `Local rembg`.

[ ] Добавить настройки Local rembg: профиль/model.

[ ] Добавить отдельный чекбокс `Удалять контур` и выбор `1/2/3 px`.

[ ] Подключить новые поля к сохранению настроек.

### Этап 3. Local Real-ESRGAN

[ ] Реализовать проверку пути к `realesrgan-ncnn-vulkan.exe`.

[ ] Реализовать запуск через `subprocess.run`.

[ ] Сохранять результат в `raw/`.

[ ] Логировать команду без лишнего шума и без секретов.

[ ] Обработать ошибки: exe не найден, models не найдены, output не создан.

### Этап 4. Local rembg

[ ] Импортировать `rembg` лениво, чтобы приложение запускалось даже при проблеме с моделью.

[ ] Создавать `new_session()` один раз на batch.

[ ] Реализовать local remove background для одного файла.

[ ] Сохранять PNG с alpha.

[ ] Добавить понятный log для первого запуска модели.

### Этап 5. Edge shrink

[ ] Реализовать `shrink_alpha_edges`.

[ ] Подключить этап после удаления фона.

[ ] Разрешить запуск edge shrink без удаления фона, если вход уже PNG с alpha.

[ ] Ограничить значения до `1..3`.

### Этап 6. Pipeline integration

[ ] Поддержать KIE-only старый сценарий без изменения поведения.

[ ] Поддержать local-only сценарий без KIE API Key.

[ ] Поддержать смешанные сценарии local -> KIE и KIE -> local.

[ ] Обновить проверку `needs_kie_api`, чтобы KIE API Key требовался только если реально выбран KIE-этап.

### Этап 7. Документация

[ ] Обновить `PROJECT_KNOWLEDGE_BASE.md` или отдельную wiki/project page ссылкой на это ТЗ.

[ ] Добавить короткую инструкцию для автора:

```text
1. Скачай/положи Real-ESRGAN в папку проекта.
2. В настройках выбери Local Real-ESRGAN.
3. Для клипартов выбери Clipart + 2x/4x.
4. Для удаления фона выбери Local rembg + Clipart.
5. Включи Удалять контур 1 px.
```

### Этап 8. Проверка

[ ] Запустить `python -m py_compile .\main.py`.

[ ] Прогнать одну тестовую картинку через local-only pipeline.

[ ] Прогнать одну тестовую картинку через mixed pipeline.

[ ] Проверить результат на темном фоне.

[ ] Проверить, что в git не попали бинарники Real-ESRGAN.

## 11. Решение по Photoroom

Добавить `PhotoRoom Standard` как отдельный платный fallback для изображений, где локальные модели дают неприемлемый край.

- API: `POST https://sdk.photoroom.com/v1/segment`.
- Режим: Standard, PNG/RGBA, полный размер.
- Ключ: отдельное скрытое поле с замком в настройках.
- Цена по документации на момент решения: `$0.02` за успешную обработку изображения.
- PhotoRoom не заменяет локальные варианты и используется только при явном выборе пользователя.

## 12. Рекомендуемый MVP

Самая короткая полезная версия:

1. `.gitignore` для папки Real-ESRGAN.
2. Local Real-ESRGAN как третий вариант апскейла.
3. Local rembg как второй вариант удаления фона.
4. Edge shrink 1/2/3 px.
5. Исправление проверки KIE API Key для local-only режима.
6. Проверка на 2-3 картинках.

Это даст максимум пользы без полной переработки приложения.

## 13. Addendum: Fixed Order and Unsharp Mask

The processing order is fixed:

1. optional local visible-mark cleanup;
2. optional upscale before background removal;
3. optional Unsharp Mask;
4. remove background;
5. optional upscale after background removal;
6. edge contour removal;
7. final trim.

The trim timing selector is removed from the UI. Trim always runs at the end.

Unsharp Mask runs after the optional first upscale and before background removal. Manual settings are available:

- `Amount`;
- `Radius`;
- `Threshold`.

Starting preset for watercolor clipart: `Amount 30`, `Radius 100`, `Threshold 0`.
