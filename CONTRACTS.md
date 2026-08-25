# CONTRACTS.md

Интерфейсы между модулями: входы/выходы, форматы JSON, названия эндпоинтов/функций. Любая межмодульная задача сначала получает контракт здесь, потом реализацию. Worker и Manager другого модуля ориентируются на этот файл вместо чтения чужого кода.

Статус: **рабочий черновик**. Реализованные контракты помечаются по мере прохождения этапов.

В архитектурных описаниях допустимы названия `ai-clipping`, `text-gen`, `video-effects`, `analytics-learning`.
Реальные Python package/directory names всегда: `ai_clipping`, `text_gen`, `video_effects`, `analytics_learning`.

---

## Формат записи контракта

```
### <module_A> → <module_B>: <название>
- Триггер: когда вызывается
- Вход: поля и типы
- Выход: поля и типы
- Ошибки: что может пойти не так и как это отражается в ответе
- Статус: черновик / реализовано / изменено (дата)
```

---

## Core domain entities / shared IDs

Это контракты и доменные сущности для Stage 0–1, не SQLAlchemy-реализация.

### Video
- `id`
- `source_path` / `storage_key`
- `original_filename`
- `status`
- `created_at`

### Clip
- `id`
- `video_id`
- `start`
- `end`
- `status`
- `created_at`

### Job
- `id`
- `type`
- `status`
- `entity_id`
- `error`
- `created_at`
- `updated_at`

### RenderedAsset
- `id`
- `clip_id`
- `storage_key`
- `format`
- `width`
- `height`
- `duration`
- `created_at`

### PlatformAccount
- `id`
- `platform`
- `external_account_id`
- `display_name`
- `encrypted_credentials`
- `status`

### Publication
- `id`
- `clip_id`
- `account_id`
- `external_post_id`
- `status`
- `scheduled_at`
- `published_at`
- `error`

---

## Stage 1 MVP pipeline

Stage 1 не зависит от `ai_clipping` и `text_gen`. Первый pipeline:

```
manual video upload
→ Video
→ manual clip timestamps
→ Clip
→ video-effects
→ RenderedAsset
→ manual publishing to one platform
→ Publication
```

AI clipping и text generation подключаются на следующих стадиях.

---

## Stage 1 API contracts

### client → ingestion: `UploadVideo`
- Stage: Stage 1.1
- Endpoint: `POST /videos`
- Content-Type: `multipart/form-data`
- Вход: поле `file` с одним локально загруженным видеофайлом
- Выход: `{ id, original_filename, status, created_at }`
- Ошибки: отсутствует файл / пустой файл / неподдерживаемый media type или расширение / превышен configurable upload size limit
- Статус: реализовано 2026-08-25

### client → ingestion: `GetVideo`
- Stage: Stage 1.1
- Endpoint: `GET /videos/{video_id}`
- Вход: `video_id`
- Выход: `{ id, original_filename, status, created_at }`
- Ошибки: `404`, если видео не найдено
- Статус: реализовано 2026-08-25

---

## Заготовки контрактов будущих AI/automation stages

### ingestion → ai-clipping: `TranscriptSegments`
- Stage: будущий Stage 3+
- Триггер: после завершения транскрипции и scene detection для видео
- Вход: `video_id`
- Выход: `{ video_id, segments: [{ start, end, text, speaker?, scene_boundary: bool }] }`
- Ошибки: видео не транскрибировано / повреждён файл
- Статус: черновик

### ai-clipping → text-gen: `ClipCandidate`
- Stage: будущий Stage 3+
- Триггер: после ранжирования сегментов
- Вход: `video_id`
- Выход: `{ video_id, candidates: [{ start, end, score, reason }] }`
- Ошибки: нет кандидатов выше порога
- Статус: черновик

### text-gen → video-effects: `ClipMeta`
- Stage: будущий Stage 2+
- Триггер: после генерации текста под клип
- Вход: `clip_id`
- Выход: `{ clip_id, title, description, hashtags: [], subtitle_track: [{ start, end, text }] }`
- Ошибки: LLM недоступен / превышен лимит длины под платформу
- Статус: черновик

### video-effects → publisher: `RenderedClip`
- Stage: Stage 1 для ручной публикации и будущий Stage 5 для автопостинга
- Триггер: после завершения рендера
- Вход: `clip_id`
- Выход: `{ clip_id, file_url, duration, format, platform_target }`
- Ошибки: сбой рендера ffmpeg, неверное соотношение сторон
- Статус: черновик

### publisher → analytics-learning: `PublishedPost`
- Stage: будущий Stage 6+
- Триггер: после успешной публикации
- Вход: `clip_id, account_id`
- Выход: `{ post_id, platform, account_id, clip_id, published_at }`
- Ошибки: сбой публикации, rate limit платформы
- Статус: черновик

### analytics-learning → ai-clipping: `PatternWeights`
- Stage: будущий Stage 7
- Триггер: периодически (батч), после накопления новых метрик
- Вход: диапазон дат / account_id
- Выход: `{ feature_weights: {...}, updated_at }`
- Ошибки: недостаточно данных для пересчёта
- Статус: черновик — активируется на Этапе 7

### dashboard → все модули: read-only API
- Stage: будущий Stage 4+
- Триггер: запрос интерфейса
- Вход: зависит от вьюхи (список аккаунтов / клипов / метрик)
- Выход: агрегированные данные, без прав на изменение бизнес-логики
- Статус: черновик
