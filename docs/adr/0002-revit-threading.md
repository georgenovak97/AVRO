# ADR 0002 — Границы потоков и lifecycle для Revit API

Статус: Accepted  
Дата: 2026-08-12

## Контекст

Family Browser использует WPF UI, background workers (scan/preview/cache) и вызовы Revit API.
В прошлых итерациях перенос кода `Closing`/cleanup и lifecycle-логики приводил к нестабильности превью и аварийному завершению Revit.

Нужны жёсткие правила, что можно выполнять в фоне, а что обязано выполняться только в main thread Revit.

## Решение

### 1) Только main thread Revit

Следующие операции выполняются только в main thread (UI/Revit контекст):
- `OpenDocumentFile`;
- `FilteredElementCollector` по Revit Document;
- `LoadFamily`;
- `Transaction` и любые commit/rollback операции;
- `PromptForFamilyInstancePlacement`;
- любые обращения к объектам Revit API (`Autodesk.Revit.DB.*`, `Autodesk.Revit.UI.*`).

### 2) Допустимо в background thread

- `os.walk` и файловое сканирование;
- чтение/запись JSON/PNG cache;
- извлечение и декодирование preview-байтов без Revit API;
- чистые вычисления и фильтрация данных.

### 3) Публикация результатов в UI

- Worker публикует результат только через Dispatcher.
- Результат применяется только при актуальном generation id.
- При несовпадении generation результат игнорируется.

### 4) Правила закрытия окна (Closing)

- В `Closing` нельзя делать `Join`, `Abort`, блокирующие ожидания.
- `Closing` только:
  - помечает generation/disposed;
  - отписывает listeners;
  - запускает best-effort асинхронные сохранения без блокировки UI.

### 5) Запрещённые изменения без отдельного stress-теста

- Перенос/рефакторинг `show()` reopen loop;
- изменение связки `ShowDialog -> pending placement -> reopen`;
- перенос lifecycle-обработчиков между модулями без воспроизводимого regression-теста.

## Последствия

Плюсы:
- меньше crash-рисков Revit;
- предсказуемое поведение при close/reopen;
- безопаснее будущая модульная декомпозиция.

Минусы:
- ограничивает скорость «быстрых» рефакторингов;
- требует дисциплины с generation guards и ручного Revit smoke/stress теста.

## Guardrails

- Любой PR с изменением threading/lifecycle обязан иметь:
  1) явный список затронутых обработчиков;
  2) ручной Revit stress-test (минимум 20 циклов open/close при фоновой активности);
  3) rollback-план через `git revert`, без переписывания истории `develop`.
