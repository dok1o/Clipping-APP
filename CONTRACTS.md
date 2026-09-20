# CONTRACTS — доменные сущности, БД, API

> Приоритет: MASTER_SPEC > **CONTRACTS** > ARCHITECTURE > AGENTS > KNOWLEDGE > PROGRESS.
> Contract-first: любое изменение поведения/схемы/API — сначала здесь, затем код в том же тикете.

## 1. Общие конвенции

- Python: файлы/функции/переменные — `snake_case`. Таблицы БД — `snake_case` **множественное число** (`videos`, `clips`, ...).
- PK — UUIDv4 (Python `uuid4`, тип `sa.Uuid()` → PG `UUID`, SQLite `CHAR(32)`).
- Timestamps — `timestamptz` (`DateTime(timezone=True)`), UTC, `created_at` default now, `updated_at` onupdate now. В API — ISO8601 UTC **с Z** (`2026-09-20T12:00:00Z`).
- **Статусы: `varchar` + `CHECK`** (не native PG enum) — единый стиль на всех СУБД (ADR-003). В коде — классы строковых констант; в Pydantic — `Literal`.
- JSONB: `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")` (PG=JSONB, SQLite=JSON) — одинаково в моделях и миграциях.
- Миграции: только Alembic, отдельная ревизия на изменение, upgrade/downgrade обязаны работать (тест `test_migrations.py` сравнивает схему из миграций со схемой из метаданных моделей).
- `create_all` запрещён в прод-коде (только тест сравнения схем).
- Пагинация: `limit` (default 20, max 100) + `offset` (default 0).
- Единый формат ошибок:
  ```json
  {"detail": {"code": "snake_case_code", "message": "human readable", "fields": {"field": "why"}}
  ```
  `fields` — `null` или словарь. Ошибка валидации FastAPI → 422 `{"code": "validation_error", "fields": {...}}`.

## 2. Сущности (Stage 0–1)

### 2.1 Video — `videos`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | uuid4 |
| original_filename | varchar(255) | как прислал пользователь |
| storage_key | varchar(512) **unique** | `videos/{video_uuid}/{safe_name}` |
| size_bytes | bigint | >0 |
| mime_type | varchar(64) | allowlist: video/mp4, video/quicktime, video/webm, video/x-matroska |
| duration_sec | float null | из ffprobe (опционально; null если ffprobe недоступен/ошибка) |
| width, height | int null | из ffprobe |
| status | varchar(16) + CHECK | `uploading | ready | failed | deleted` |
| error_message | text null | |
| created_at / updated_at | timestamptz | |

Индекс: `ix_videos_status`.
**Жизненный цикл:** `uploading` (строка создаётся при приёме файла) → `ready` (S3 upload + опц. ffprobe) | `failed` (storage_error). Удаление Video — soft (`deleted`); FK `RESTRICT` защищает от физического удаления при существующих clips (ADR FK).

### 2.2 Clip — `clips`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| video_id | UUID FK→videos.id, ondelete RESTRICT | indexed |
| title | varchar(140) | 1..140 |
| start_sec, end_sec | float | CHECK `start_sec >= 0`, CHECK `end_sec > start_sec` |
| status | varchar(16) + CHECK | `draft | render_queued | rendering | rendered | render_failed` |
| score | float null | Stage 3+ |
| features | JSONB null | Stage 3+ |
| created_at / updated_at | timestamptz | |

Индекс: `ix_clips_video_id_status (video_id, status)`.
Валидация длительности (уровень сервиса, конфиг `CLIP_MIN_SEC=5`, `CLIP_MAX_SEC=180`): `clip_too_short` / `clip_too_long`; `end_sec <= video.duration_sec` — только если duration известна (ffprobe НЕ вызывается в этом flow).

### 2.3 Job — `jobs`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| type | varchar(16) + CHECK (attr `job_type`, колонка `type`) | `transcribe | render | text_gen | publish | metrics_sync | train` |
| ref_type | varchar(16) | `video | clip | publication | candidate` (полиморфная ссылка, без FK) |
| ref_id | UUID | |
| status | varchar(12) + CHECK | `queued | running | succeeded | failed | retrying | cancelled` |
| attempts, max_attempts | int | default 0 / 3 |
| idempotency_key | varchar(255) **unique null** | |
| payload / result | JSONB null | |
| error_message | text null | без секретов, stderr-хвост ≤2KB |
| scheduled_at / started_at / finished_at | timestamptz null | |
| created_at / updated_at | timestamptz | |

Индексы: `ix_jobs_status_type (status, type)`, `ix_jobs_ref (ref_type, ref_id)`.

### 2.4 RenderedAsset — `rendered_assets`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| clip_id | UUID FK→clips.id, ondelete **CASCADE** | indexed |
| storage_key | varchar(512) unique | `renders/{clip_id}/{asset_id}.mp4` |
| size_bytes | bigint | |
| width / height | int | 1080 / 1920 |
| codec_video / codec_audio / pix_fmt | varchar(16) | `h264` / `aac` / `yuv420p` |
| duration_sec | float | end−start |
| status | varchar(12) + CHECK | `rendering | ready | failed` |
| created_at | timestamptz | |

### 2.5 PlatformAccount — `platform_accounts`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| platform | varchar(16) + CHECK | `youtube | tiktok` |
| external_account_id | varchar(255) | **unique (platform, external_account_id)** |
| display_name | varchar(255) null | |
| credentials_encrypted | text | Fernet; **никогда** в логах/API (в ответах — `***`) |
| scopes | JSONB | список scope строк |
| expires_at | timestamptz null | |
| is_active | bool | |
| created_at / updated_at | timestamptz | |

### 2.6 Publication — `publications`
| Поле | Тип | Правила |
|---|---|---|
| id | UUID PK | |
| clip_id | UUID FK→clips.id, ondelete RESTRICT | |
| rendered_asset_id | UUID FK→rendered_assets.id null, ondelete SET NULL | |
| platform_account_id | UUID FK→platform_accounts.id, ondelete RESTRICT | |
| platform | varchar(16) + CHECK | `youtube | tiktok` |
| external_post_id | varchar(255) null | ID поста на платформе |
| status | varchar(16) + CHECK | `draft | scheduled | uploading | published | failed | cancelled` |
| scheduled_at, published_at | timestamptz null | |
| idempotency_key | varchar(255) **unique** | `{clip_id}:{platform}:{asset_id}:{sha256(title)[:12]}` (фиксация Stage 1.4) |
| attempt_count | int | |
| last_error | text null | без секретов |
| metadata | JSONB null (attr `meta`, колонка `metadata`) | title/desc/tags/privacy |
| created_at / updated_at | timestamptz | |

Индексы: `ix_publications_clip_platform_status (clip_id, platform, status)`;
**Partial unique**: `uq_publications_active` — UNIQUE `(clip_id, platform)` WHERE `status NOT IN ('cancelled','failed')` (одна «активная» публикация на клип+платформу).

### 2.7 Будущие сущности (фиксация вперёд)
- **TranscriptSegment** (Stage 3): `transcript_segments(id, video_id FK, start, end, text, avg_confidence, words JSONB)`.
- **ClipCandidate** (Stage 3): `clip_candidates(id, video_id FK, start, end, score, features JSONB, reason)`.
- **Metric** (Stage 6): `metrics(id, publication_id FK, captured_at, views, likes, comments, shares, raw JSONB)`, индекс `(publication_id, captured_at)`.
- **MlModel** (Stage 7): `ml_models(version unique, storage_key, metrics JSONB, trained_at, is_active, fallback_reason)`; активна ровно одна.

## 3. FK / delete-политика (ADR-FK)

| FK | Поведение | Обоснование |
|---|---|---|
| clips.video_id → videos | RESTRICT | удаление Video — soft (`status=deleted`); физическое удаление запрещено при клипах; покрыто тестом |
| rendered_assets.clip_id → clips | CASCADE | артефакты рендера не имеют смысла без клипа |
| publications.clip_id → clips | RESTRICT | публикации — бизнес-записи, не терять |
| publications.rendered_asset_id | SET NULL | публикация переживает удаление ассета |
| publications.platform_account_id | RESTRICT | история публикаций не отвязывается от аккаунта |

## 4. API v1 (Stage 0–1 реализовано; расширения — аддитивно)

Базовый префикс `/api/v1`. Даты — ISO8601 UTC c `Z`.

### 4.1 GET /health → 200
```json
{"status": "ok", "version": "0.1.0", "checks": {"db": "ok", "redis": "skip", "s3": "ok"}}
```
`checks.*` ∈ `ok | skip` (skip = сервис недоступен/не настроен; liveness всегда 200).

### 4.2 POST /api/v1/videos — загрузка (multipart/form-data, поле `file`)
- Лимит `UPLOAD_MAX_MB` (default 1024); allowlist mime `video/mp4|video/quicktime|video/webm|video/x-matroska` + расширение `.mp4|.mov|.webm|.mkv`; потоковая запись чанками 1MB во временный файл (не в RAM), затем stream-upload в S3.
- Content-Length > лимит (+2MB slack на multipart) → 413 **до** полной записи.
- Ключ: `videos/{uuid}/{safe_name}`; safe_name: lower, `[a-z0-9._-]`, ≤80 симв (санитизация).
- ffprobe для Video **разрешён** на этом шаге (запрет касается только manual-clip валидации); при недоступности/ошибке — `duration_sec: null`, статус `ready`.
- Ответ **201** `VideoRead`:
```json
{"id": "…uuid…", "original_filename": "video.mp4", "storage_key": "videos/…/video.mp4",
 "size_bytes": 1048576, "mime_type": "video/mp4", "duration_sec": 12.5, "width": 1280,
 "height": 720, "status": "ready", "error_message": null,
 "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-20T10:00:00Z"}
```
- Ошибки: `400 empty_file`, `413 payload_too_large`, `415 unsupported_media`, `500 storage_error`.

### 4.3 GET /api/v1/videos?limit=&offset= → 200
```json
{"items": [VideoRead, ...], "total": 42}
```

### 4.4 GET /api/v1/videos/{video_id} → 200 VideoRead / 404 `video_not_found` / 422 (невалидный UUID)

### 4.5 POST /api/v1/videos/{video_id}/clips/manual
```json
{"title": "Best moment", "start_sec": 12.5, "end_sec": 42.0}
```
→ **201** `ClipRead` (status `draft`). Ошибки: `400 invalid_range | clip_too_short | clip_too_long`, `404 video_not_found`, `409 video_not_ready`. ffprobe в этом flow **не вызывается** (проверено grep + mock-тестом).
```json
{"id": "…", "video_id": "…", "title": "Best moment", "start_sec": 12.5, "end_sec": 42.0,
 "status": "draft", "score": null, "features": null,
 "created_at": "2026-09-20T10:01:00Z", "updated_at": "2026-09-20T10:01:00Z"}
```

### 4.6 GET /api/v1/clips?video_id=… → 200 `{"items": [ClipRead]}`; GET /api/v1/clips/{clip_id} → 200 / 404 `clip_not_found`

### 4.7 POST /api/v1/clips/{clip_id}/render → 202
```json
{"job_id": "…uuid…", "clip_id": "…uuid…", "status": "render_queued"}
```
- Clip: `draft|render_failed` → постановка в Job(type=render); `render_queued|rendering` → **409 already_rendering**; `rendered` → **идемпотентный ответ 202** с существующим succeeded job (`status: "rendered"`); `rendered` без готового asset → 422 `invalid_clip_state`; video не ready → 422 `invalid_clip_state`.
- Повторный render после `render_failed` разрешён (новый job с ключом `render:{clip_id}:{n}`).
- Статус опрашивается `GET /api/v1/jobs/{job_id}`; результат в `result.asset_id`.

### 4.8 GET /api/v1/renders/{asset_id} → 200 RenderedAssetRead / 404 `asset_not_found`
### 4.9 GET /api/v1/renders/{asset_id}/download → 200
```json
{"url": "https://…presigned…", "expires_sec": 900}
```
(S3 — presigned URL; фиксация. Локальный file-режим не предусмотрен.)

### 4.10 GET /api/v1/jobs/{job_id} → 200 JobRead / 404 `job_not_found`
```json
{"id": "…", "type": "render", "status": "succeeded", "ref_type": "clip", "ref_id": "…",
 "attempts": 1, "max_attempts": 3, "idempotency_key": "render:…", "payload": {…},
 "result": {"asset_id": "…"}, "error_message": null,
 "scheduled_at": null, "started_at": "…", "finished_at": "…",
 "created_at": "…", "updated_at": "…"}
```

### 4.11 Публикации (Stage 1.4, контракт зафиксирован)
- `POST /api/v1/publications/manual` body:
```json
{"clip_id": "…", "platform": "youtube", "platform_account_id": "…", "title": "…",
 "description": "…", "privacy": "public", "scheduled_at": null}
```
→ 201 PublicationRead (status `uploading` при немедленной загрузке | `scheduled` при `scheduled_at`). Ошибки: `404 clip_not_found | asset_not_found | account_not_found`, `409 duplicate_publication`, `422 validation_error`, `502 platform_error` (с last_error без секретов).
- `GET /api/v1/publications?clip_id=&platform=`, `GET /api/v1/publications/{id}` → 200/404.
- Идемпотентность: unique `idempotency_key`; повторный POST с тем же ключом → 409 `duplicate_publication` (фиксация).

### 4.12 Будущие эндпоинты (фиксация)
- Stage 2: `POST /api/v1/texts/generate` → `{"job_id": null, "texts": {…}}` (Stage 2 синхронно; Stage 5 — через Job, контракт сохраняет оба поля); `GET /api/v1/clips/{id}/texts?platform=`.
- Stage 3: `POST /api/v1/videos/{id}/transcribe` → 202+Job; `GET /api/v1/videos/{id}/transcript`; `POST /api/v1/videos/{id}/candidates?top_k=5`; `POST /api/v1/candidates/{id}/promote`.
- Stage 5: Beat/расписание, rate limits, Redis-lock, `reconcile_stuck_jobs`.
- Stage 6: `POST /api/v1/publications/{id}/sync-metrics` → 202; `GET /api/v1/publications/{id}/metrics`.
- Stage 7: `POST /api/v1/ml/train` → 202; `GET /api/v1/ml/models`; `POST /api/v1/ml/models/{v}/activate`; `GET /api/v1/ml/dataset/stats`.

## 5. Render spec (Stage 1.3, канон)

- Выход: MP4, `-c:v libx264 -preset veryfast -crf 23`, `-c:a aac -b:a 128k`, 1080x1920, `-pix_fmt yuv420p`, `-movflags +faststart`, `-r 30` (фиксация: форс 30 fps).
- Фильтр: `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1` (center-crop).
- Порядок аргументов: быстрый seek `-ss {start}` **до** `-i`, точная обрезка `-t {duration}` после `-i` (фиксация).
- Только `services/render/ffmpeg_runner.py` запускает subprocess: list-args, `shell=False`, `timeout=FFMPEG_TIMEOUT_SEC`, stderr-хвост ≤2KB в лог/Job (не в API полностью).
- Controlled errors: `ffmpeg_missing`, `render_timeout`, `render_failed`, `invalid_timestamps` → Job failed + Clip `render_failed`, API не падает.
