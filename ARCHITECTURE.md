# ARCHITECTURE.md

Обновляется только при изменении структуры модулей — не при каждом коммите. Источник истины по устройству системы; при конфликте с описанием в чате приоритет у этого файла.

---

## Общая схема данных (целевая, высокоуровнево)

```
[источник видео] → ingestion → ai-clipping → text-gen → video-effects → publisher → [соцсети]
                                                                             ↓
                                                                   analytics-learning
                                                                             ↓
                                                                     dashboard (чтение)
```

`analytics_learning` собирает метрики опубликованных клипов и передаёт приоритезацию обратно в `ai_clipping` (замкнутый цикл обучения — вступает в силу на Этапе 7).

Для MVP Stage 1 используется pipeline без AI:

```
manual video upload → Video → manual clip timestamps → Clip → video-effects → RenderedAsset → manual publishing to one platform → Publication
```

Stage 1 не зависит от `ai_clipping` и `text_gen`; AI clipping и text generation подключаются на следующих стадиях.

---

## Модули и границы ответственности

| Модуль | Отвечает за | НЕ отвечает за |
|---|---|---|
| `ingestion` | Приём видео, извлечение аудио, транскрипция, scene detection | Выбор "лучших" моментов — это `ai_clipping` |
| `ai_clipping` | Ранжирование сегментов по потенциальной виральности | Рендер видео, тексты |
| `text_gen` | Заголовки/описания/хэштеги/субтитры | Монтаж видео |
| `video_effects` | Кроп, субтитры на видео, переходы, watermark, рендер (ffmpeg) | Публикацию |
| `publisher` | API соцсетей, очередь публикаций, retry, хранение токенов | Выбор контента |
| `analytics_learning` | Сбор метрик, поиск паттернов | Публикацию, монтаж |
| `dashboard` | Отображение состояния (read-only к остальным модулям через API) | Бизнес-логику модулей |
| `infra` | Очереди (Redis/Celery), хранилище (S3), схема БД, деплой | Продуктовую логику |

Полное описание контрактов между модулями — в `CONTRACTS.md`. Этот файл не дублирует интерфейсы, только границы ответственности и общую схему.

В архитектурных описаниях допустимы названия `ai-clipping`, `text-gen`, `video-effects`, `analytics-learning`.
Реальные Python package/directory names всегда: `ai_clipping`, `text_gen`, `video_effects`, `analytics_learning`.

---

## Структура репозитория (план, актуализировать по факту)

```
backend/
├── app/
│   ├── ingestion/
│   ├── ai_clipping/
│   ├── text_gen/
│   ├── video_effects/
│   ├── publisher/
│   ├── analytics_learning/
│   ├── infra/
│   └── main.py
├── tests/
frontend/        # React-дашборд
storage/         # локальные видео и промежуточные файлы, не коммитить
AGENTS.md
PROGRESS.md
ARCHITECTURE.md
CONTRACTS.md
```

---

## Технологические решения и почему

- **PostgreSQL**, а не NoSQL — данные сильно реляционные (аккаунты ↔ видео ↔ клипы ↔ метрики).
- **Celery/Redis**, а не синхронная обработка — рендер видео и транскрипция тяжёлые по CPU, не должны блокировать API.
- **faster-whisper**, а не оригинальный openai-whisper — быстрее при сопоставимом качестве.
- Эвристики в `ai_clipping` до Этапа 7, а не сразу модель — не на чём обучаться без реальных метрик.

---

## История значимых архитектурных решений

- 2026-08-25 — Зафиксирована исходная схема модулей и roadmap (см. AGENTS.md). Реализация не начата.
