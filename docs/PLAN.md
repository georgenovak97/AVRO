# AVRO Extension — актуальный план исправлений

Дата ревью: 2026-08-20
Версия кода: `1.3`, commit `3f932bf`
Поддерживаемые версии Revit: **2020–2025**
Runtime: pyRevit 4.8+, IronPython 2.7

Этот документ заменяет предыдущий план. Он составлен по результатам полного
code review текущего репозитория AVRO. Код во время ревью не изменялся.

## Статус ревью

### Автоматические проверки

Все команды выполнены из каталога `AVRO/` и завершились успешно:

```text
python3 scripts/check.py                         PASS
python3 -m unittest discover -s tests -p 'test_*.py' -v   PASS (50 tests)
~/.local/bin/ruff check .                        PASS
python3 scripts/verify_family_browser.py         PASS
git diff --check                                 PASS
```

Unit-тесты работают в CPython 3 без Revit/CLR. Они подтверждают чистую логику,
но не заменяют smoke-тест в Revit.

### Git-состояние на момент ревью

- AVRO — отдельный git-репозиторий.
- Ветка: `main`, синхронизирована с `origin/main`.
- Рабочее дерево до этой записи было чистым.
- Внешний workspace содержит AVRO как untracked-каталог родительского git;
  коммиты выполняются только в `AVRO/.git`.

## Приоритеты

### HIGH — исправить до smoke/release

#### H1. Неопределённая переменная `total`

- Файл: `AVRO.tab/02_Tools.panel/FamilyBrowser.pushbutton/script.py:805`.
- `_restore_window_focus()` вызывает `i18n.t("from_cache", n=total)`, но
  `total` не определён ни в методе, ни в модуле.
- Метод вызывается после полного сканирования и после загрузки кэша. Поэтому
  ошибка возникает на обоих основных путях успешного открытия браузера.
- Симптом: необработанный `NameError` через Dispatcher после построения каталога;
  статус не обновляется, ошибка попадает в Revit/pyRevit журнал.
- Минимальное исправление: вычислять `len(self._scan.get("all", []))` внутри
  метода или передавать число явным параметром.
- Тесты после исправления:
  - добавить CPython-совместимый статический/runtime guard для вычисления
    статуса, если entry point можно безопасно изолировать;
  - Revit 2020: первое открытие после полного скана;
  - Revit 2020 и 2025: повторное открытие из кэша;
  - проверить журнал на отсутствие `NameError`.

### MEDIUM — исправить до release или явно принять риск

#### M1. Имена транзакций не имеют префикса `AVRO: `

- Файлы: `lib/i18n.py:211-213,426-428`, вызовы в
  `script.py:2313,2327,2458-2459`.
- Текущие имена: «Активация типа семейства», «Загрузка семейства» и
  локализованные варианты без `AVRO: `.
- Это нарушает правило `AVRO/AGENTS.md` и release checklist; действия трудно
  отличить в Undo.
- Минимальное исправление: централизованно добавлять `AVRO: ` к именам
  `Transaction`, сохраняя локализованный хвост.
- Тесты: статический guard на все `Transaction(doc, ...)`; ручная проверка Undo
  в Revit 2020 и 2025.

#### M2. Частично неудачная инспекция может стать usable meta

- Файл: `lib/family_inspector.py:323-449`.
- `_inspect_document()` устанавливает `meta["ok"] = True` до выполнения
  отдельных блоков. Ошибки отдельных collectors/FamilyManager подавляются,
  а некоторые счётчики остаются `0` из `_empty_meta`.
- При активном STRICT quality flag такой счётчик выглядит как подтверждённый
  ноль и может дать ложный pass вместо unknown/fail.
- Минимальное исправление: для невычисленных счётчиков использовать `None`;
  разделить «документ открылся» и «поле успешно инспектировано» либо выставлять
  `ok=True` только после обязательных блоков.
- Тесты:
  - partial-inspection meta с ошибкой FamilyManager;
  - каждый `limit_*` с отсутствующим/`None` счётчиком;
  - позитивные нулевые значения после успешной инспекции;
  - ручная проверка повреждённого/неполного RFA в Revit 2020/2025.

#### M3. Повторная загрузка не классифицируется как already loaded

- Файл: `script.py:2466-2476`.
- `_load_family_element()` возвращает непустую ошибку на любом неуспешном
  `LoadFamily`, поэтому ветка `skipped.append(...)` фактически недостижима.
- Уже загруженное семейство может отображаться как `not_loaded`, а не как
  `already_in_project`.
- Минимальное исправление: отличать отказ/отмену/ошибку от уже существующего
  семейства через явный результат или проверку проекта.
- Тест: загрузить одно семейство, повторить действие и проверить сообщение;
  отдельно проверить reload с изменёнными параметрами.

#### M4. Документация обещает удалённую фильтрацию

- `README.md:10-13` описывает filter axes, constraints, double-click и Load
  button.
- `AVRO.tab/02_Tools.panel/FamilyBrowser.pushbutton/bundle.yaml` содержит
  tooltip `Search, filter by category, double-click to place in project`.
- В текущем `ui.xaml` фильтры отсутствуют; CHANGELOG фиксирует, что filtering
  был удалён, а фактический путь — левый клик для размещения и правый клик для
  свойств.
- Минимальное исправление: синхронизировать README и bundle tooltip с текущим
  интерфейсом либо вернуть фильтры отдельной задачей с UI и тестами.
- Тест: проверить текст README/tooltip и ручной осмотр ribbon в Revit.

#### M5. Повторная загрузка всегда перезаписывает значения параметров

- Файл: `lib/family_load_options.py:27-29`.
- `OnFamilyFound()` всегда выставляет `overwriteParameterValues=True`.
- Это может заменить пользовательские значения параметров уже загруженного и
  изменённого семейства. Поведение выглядит намеренным, но пользователь не
  получает подтверждения.
- Варианты минимального решения:
  - оставить поведение, но явно документировать overwrite;
  - добавить подтверждение перед reload;
  - разделить обычную загрузку и явный reload.
- Тест: ручной Revit smoke с изменённым параметром уже загруженного семейства.

### LOW — плановая гигиена

#### L1. Большой объём мёртвого кода после удаления фильтров

В `FamilyBrowser.pushbutton/script.py` не имеют callers или являются пустыми:

- `clear_library_cache`;
- `_fill_quality_flags`, `_read_quality_flags`;
- `_passes_quality_flags`, `_apply_quality_flag_filters`, `_meta_int`;
- `_fill_check_list`, `_checked_keys_from_panel`, `_sync_filters_from_ui`;
- `_close_filters_popup`;
- `_all_families`, `_mods`, `_toggle_path`, `_range_paths`;
- `_update_selection_status`, `_on_clear_search`;
- `_load_selected`, `_load_family`, `_load_families`, `_get_family_symbol`.

Также атрибуты `_category_filter_keys`, `_host_filter_keys`,
`_work_plane_filter_keys`, `_shared_nested_filter_keys` загружаются/сохраняются,
но не участвуют в текущем UI.

В `lib/family_inspector.py` сохранены неиспользуемые текущим UI оси
category/hosting/placement и tri-state options. Не удалять механически: сначала
решить, будет ли фильтрация возвращаться. Если нет, удалить одним отдельным
cleanup commit вместе с устаревшими тестами и документацией.

#### L2. Нелокализованный заголовок MessageBox

- `script.py:1373-1377` использует `config.APP_NAME`, всегда русский текст.
- Использовать `i18n.t("app_title")`.
- Тест: английская и русская локализация в UI smoke.

#### L3. Магический порог размера

- `script.py:1291-1292` содержит `15 * 1024` напрямую.
- Вынести в именованную константу, если size filter будет возвращён; иначе
  удалить вместе с мёртвым фильтром.

#### L4. Избыточная проверка в `limit_ref_planes`

- `lib/family_browser_quality.py:146-163` имеет дублирующий check
  `is_meta_usable` после `_meta_int`.
- Исправлять только при следующем изменении модуля; функциональный риск низкий.

#### L5. Sticky-session содержит WPF bitmap objects

- `script.py:176-193,2082-2096` сохраняет `BitmapImage` в `preview_mem`.
- pyRevit sticky обычно сериализуется, а .NET bitmap не гарантированно
  pickle-safe; исключение подавляется. Проверить, действительно ли кэш
  восстанавливается, либо сохранять только PNG/пути.
- Тест: два последовательных запуска в Revit/pyRevit с большим каталогом.

#### L6. Блокирующий polling размещения

- `script.py:2395-2414` делает до 30 циклов `sleep(0.5)` на основном потоке.
- ADR 0002 запрещает менять reopen-flow без отдельного stress-теста, поэтому
  это не включать в обычный cleanup. Для изменения обязательны 20 циклов
  open/close и отдельное решение по ExternalEvent/Idling.

## План по этапам

### Этап 0 — блокирующий smoke guard

Цель: устранить гарантированное runtime-исключение без изменения архитектуры.

1. Исправить H1.
2. Добавить статический guard, который ловит неопределённые имена в критическом
   post-load пути, если это возможно без импорта CLR.
3. Запустить все автоматические проверки.
4. Проверить Revit 2020 и 2025: full scan, cache hit, reload window.

Критерий выхода: H1 отсутствует, журнал чистый, каталог открывается обоими
путями.

### Этап 1 — Revit API transaction hygiene

1. Исправить M1, сохранив локализацию имён.
2. Проверить все `Transaction`/`RollBack` в entry point и load options.
3. Уточнить M3 и поведение `LoadFamily == False`.
4. Проверить M5 и выбрать продуктовую политику overwrite.
5. Повторить unit/static checks.
6. Revit 2020 и 2025: загрузка новой семьи, повторная загрузка, отмена,
   ошибка/повреждённый RFA, проверка Undo и отсутствия незавершённой транзакции.

Критерий выхода: понятный результат для success/already-loaded/cancel/error;
в Undo отображаются `AVRO: ...`; нет потери параметров без принятой политики.

### Этап 2 — корректность strict quality metadata

1. Исправить M2 в `family_inspector.py`.
2. Добавить unit-тесты partial failure, missing keys, `None`, нулевых границ и
   всех комбинаций quality flags.
3. Проверить единицы размера, reference planes + reference lines, повреждённый
   кэш и отсутствие файла.
4. Решить, возвращается ли quality filter в продуктовый UI. Не возвращать его
   частично: потребуются XAML, binding, AND-фильтрация, coverage indicator и
   ручной тест.

Критерий выхода: active unknown никогда не проходит STRICT policy; успешный
нулевой результат отличим от отсутствующего результата.

### Этап 3 — документация и cleanup

1. Исправить M4: README, bundle tooltip, CHANGELOG/описание текущего UI.
2. Исправить L2.
3. После решения по фильтрам удалить или восстановить мёртвый стек L1 одним
   отдельным commit.
4. Вынести/удалить L3 и L4 только вместе с затрагиваемой функциональностью.
5. Проверить L5 на реальном pyRevit runtime.

Критерий выхода: README, ribbon tooltip, XAML и фактические действия совпадают;
мёртвый код либо удалён, либо явно помечен как будущий API и покрыт callers.

### Этап 4 — ручной Revit smoke/release

Обязательные версии: Revit 2020 и Revit 2025. Revit 2024 дополнительно нужен
для dark UI/API deprecation проверки.

#### Extension и окно

- extension загружается через pyRevit Reload без ошибок;
- вкладка AVRO и кнопки Settings/Family Browser видны;
- запуск на пустом и рабочем проекте;
- каталог с отсутствующим путём, пустой библиотекой и отсутствующим кэшем;
- повторный запуск после полного скана и cache hit;
- закрытие окна, повторное открытие, отсутствие двойных callbacks.

#### Каталог

- сканирование локального и network path;
- поиск по имени/папке/версии;
- сортировка и навигация по дереву;
- пустые результаты;
- файл удалён во время отображения;
- read-only и недоступный каталог;
- повреждённый RFA и отсутствующее preview.

#### Загрузка и размещение

- левый клик загружает/размещает семейство;
- уже загруженное семейство;
- семейство из более новой версии Revit;
- отмена `PromptForFamilyInstancePlacement`;
- закрытие окна во время фоновой активности;
- 20 циклов open/close с активным scan/preview/cache worker для любых изменений
  threading/lifecycle.

#### Properties/inspection

- right-click на семействе с кэшем;
- right-click без кэша и отображение loading state;
- успешный inspect;
- повреждённый/неполный RFA;
- корректные category, hosting, placement, types, nested, parameters,
  materials, formulas и file size;
- unknown не отображается как подтверждённый `No` там, где значение не было
  проверено.

#### UI

- Revit 2024/2025 dark theme;
- DPI 100%, 150%, 200%;
- минимальный размер окна и resize;
- окно не теряется за Revit;
- нет лишних модальных окон;
- нет необработанных ошибок в journal.

## Покрытие тестами

### Уже подтверждено CPython/unit-тестами

- `family_browser_quality`: 20+ сценариев strict unknown, AND, thresholds,
  size units, reference plane/line sum и dict/object inputs;
- `family_inspector`: tri-state cached values, category/version fallback;
- `library_cache`: key/hash/save/load roundtrip;
- scanner/category/family name helpers;
- card layout metrics;
- i18n.

### Требует новых CPython-тестов

- H1 post-load status path;
- M2 partial inspection/unknown counters;
- M3 classification of already-loaded family;
- `family_load_options` out-parameter fallbacks;
- `rfa_preview` PNG/JPEG/gzip parsers;
- corrupted/incomplete cache and malformed JSON;
- config read/write failures and read-only paths;
- stale cache after file/subfolder changes;
- `None`, empty and invalid types for public pure helpers.

### Невозможно подтвердить без Revit

- API thread affinity и ExternalEvent/Idling;
- реальные Transaction commit/rollback/failure handling;
- `LoadFamily`, `IFamilyLoadOptions`, overwrite behavior;
- `OpenDocumentFile`/close family document;
- placement cancellation and modal version dialogs;
- WPF owner, DPI, dark theme, dispatcher lifecycle;
- journal cleanliness and ribbon appearance.

## Ограничения и принятые правила

- Не добавлять C# без нового ADR и измеренного hotspot.
- Не использовать f-strings, walrus, `match`, annotations, `async` и прочие
  конструкции Python 3 в Revit-side коде.
- Не переносить Revit API в worker thread.
- Не подавлять реальные исключения в новых критических путях; сохранять понятное
  сообщение пользователю и traceback/контекст в журнале.
- Не считать зелёные unit-тесты доказательством Revit-совместимости.
- Любой commit по model-write/threading/lifecycle должен содержать затронутые
  handlers и ссылку на выполненный Revit smoke/stress-test.

## Итоговая оценка

Текущее состояние: **готов после исправлений**.

Автоматические проверки зелёные, но H1 — гарантированное runtime-исключение
на штатном пути загрузки каталога. До исправления H1 и проверки Revit 2020/2025
нельзя считать плагин готовым к smoke/release. После H1 следует исправить M1,
проверить M2/M3/M5 на Revit и синхронизировать документацию.
