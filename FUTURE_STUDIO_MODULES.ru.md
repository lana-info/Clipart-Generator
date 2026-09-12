# Vibix Studio — будущие направления

Updated: 2026-09-12

Этот файл хранит подтверждённые владельцем идеи, которые не должны потеряться в текущем Clipart backlog. Они не считаются функциями текущего релиза, пока не пройдут отдельное проектирование, UI-approval, тесты и acceptance.

## 1. Lettering / Typography

Статус: подтверждённое будущее направление.

Цель: отдельный workflow Studio для декоративного текста и типографики, не режим внутри Clipart.

Планируемые возможности:
- пользователь задаёт фразу либо тему/событие;
- варианты lettering style: nursery, wedding, birthday, boho, luxury, retro, seasonal и свои;
- Style / Palette / Holiday profiles переиспользуются там, где это уместно;
- обязательный readable-text QC: точная фраза, без пропусков, лишних букв и случайного текста;
- отдельные правила композиции, полей и cutout-friendly результата;
- пакеты 5 / 12 / 25 либо custom;
- собственные prompt, filenames, bundle map и export;
- возможность использовать lettering как дополнение к большому цифровому bundle, но не смешивать его автоматически с Clipart PNG.

Перед реализацией: отдельный PRD/UI mockup и проверка моделей на точность текста.

## 2. Prompt Doctor

Статус: подтверждённое будущее направление; владелец назвал идею отличной.

Цель: исправлять конкретную проблему prompt без ручного переписывания всего prompt и без автоматического платного перезапуска.

Первый набор проблем:
- объект обрезан или слишком близко к краю;
- лишние предметы / дубли;
- слишком сложная или перегруженная композиция;
- случайные разрозненные фрагменты;
- слабый или грязный край;
- слишком много тени;
- стиль ушёл от остальной коллекции;
- палитра ушла от Style/Palette Profile;
- персонаж потерял позу/характер/отличительные признаки;
- венок или рамка потеряли чистое внутреннее пространство.

Принцип: Doctor меняет только релевантный слой prompt, показывает пользователю, что именно исправлено, и не запускает генерацию без отдельного подтверждения стоимости.

Не смешивать Prompt Doctor с post-processing PNG QC: Prompt Doctor исправляет инструкцию до новой генерации, PNG QC анализирует уже полученный файл.

## 3. Product Strategy tools

Статус: future expansion после Clipart MVP.

Отдельные действия поверх готовой коллекции:
- Etsy SEO: title, tags, description, alt text;
- Listing Cover concepts: layout, headline, product-element selection, CTR-oriented checks;
- Pinterest ideas: titles, descriptions, overlays, visual directions and keyword groups;
- Bundle/product map: Full, Mini, Micro, premium expansion, suggested filenames and folders.

Эти инструменты не должны автоматически менять исходные PNG и не являются частью платной image generation.

## Общие правила будущих направлений

- Каждый materially changed UI сначала получает 1120×780 Vibix mockup и явное owner approval.
- Новые модули переиспользуют общие Style/Palette/Holiday/reference компоненты только там, где семантика совпадает.
- Не переносить чужие prompt templates один-в-один; использовать их как структурную/UX основу.
- Не смешивать output contracts: Clipart, Lettering, Patterns, Junk Journal и product-strategy действия остаются различимыми.
- Платные provider calls всегда требуют отдельного cost/consent gate; никаких скрытых повторов.
