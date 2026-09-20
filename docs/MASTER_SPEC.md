# MASTER SPEC — AI Clipper

> Главный спецификация продукта. При конфликте документов побеждает этот (приоритет: MASTER_SPEC > CONTRACTS > ARCHITECTURE > AGENTS > KNOWLEDGE > PROGRESS).

- Версия: 0.1.0
- Дата: 2026-09-20
- Статус: активная разработка по Stage 0–7

## 1. Видение

Локальный self-hosted **AI Clipper**: пользователь загружает длинное видео → получает вертикальные клипы 1080x1920 (MP4, H.264+AAC) для YouTube Shorts / TikTok с заголовками, описаниями, хэштегами и субтитрами → публикует вручную или автоматически по расписанию → собирает метрики через официальные API → система учится выбирать лучшие моменты.

Принципы:
- **Zero budget**: только open-source и локальные компоненты. Платные SaaS/API — не часть обязательного пути. Платный LLM API — НЕ часть системы.
- **Single-tenant**: один пользователь, упрощённая аутентификация; credentials платформенных аккаунтов — шифрованные (Fernet).
- **Локальное железо**: RTX 3070 8GB VRAM, 32GB RAM. Всё тяжёлое влезает в 8GB VRAM ИЛИ имеет CPU fallback. Whisper и LLM не грузятся в VRAM одновременно — только последовательно, с освобождением памяти.
- **Contract-first**: сначала контракты (CONTRACTS.md) → схемы/модели/миграции → реализация → тесты.
- **Честность**: никакие «готово/работает» без прогона тестов/скриптов; ограничения окружения фиксируются явно (KNOWLEDGE.md).

## 2. Граничные условия и out-of-scope

- Ручная загрузка исходников (mp4/mov/webm/mkv). **Нет** авто-скачивания с YouTube/TikTok.
- Публикация только через **официальные** API платформ (YouTube Data API v3, TikTok Content Posting API). Никакого скрапинга.
- Сначала реализуется **одна** платформа (выбор пользователя перед Stage 1.4), архитектура `services/publish/` обязана быть расширяемой под вторую без рефакторинга ядра.
- Нет watermark на рендерах (до отдельного решения пользователя), нет лендинга/маркетингового UI.
- Бренд-стиль не определён → нейтральный рабочий Tailwind dashboard.

## 3. Пользовательские сценарии (must support к концу Stage 7)

| # | Сценарий | Суть | Stage |
|---|----------|------|-------|
| UC-1 | Ручная загрузка | mp4/mov/webm/mkv через dashboard/API → Video(duration, resolution, storage_key) | 1 |
| UC-2 | Ручная нарезка | start_sec/end_sec + название → Clip | 1 |
| UC-3 | Вертикальный рендер | MP4 H.264+AAC 1080x1920 center-crop → RenderedAsset, скачиваемый | 1 |
| UC-4 | Тексты | title/description/hashtags/captions локальной LLM, отдельно YouTube и TikTok | 2 |
| UC-5 | Транскрипция | faster-whisper локально (GPU/CPU fallback), сегменты с таймингами | 3 |
| UC-6 | AI-подбор | эвристические кандидаты (Stage 3) → ML-ранжирование с fallback на эвристики (Stage 7) | 3/7 |
| UC-7 | Публикация | ручная (Stage 1) → автоматическая по расписанию с rate-limit/retry/идемпотентностью (Stage 5) | 1/5 |
| UC-8 | Аналитика | просмотры/лайки/комментарии только через официальные API → dashboard | 6 |
| UC-9 | Самообучение | feature dataset + локальное обучение + версионирование + безопасное подключение | 7 |

## 4. Целевой pipeline (Stage 7)

```
[manual upload Video] → [transcribe faster-whisper] → [scene detect]
  → [heuristic candidates + ML rerank (fallback heuristic)]
  → [local text_gen titles/desc/tags/subs] → [ffmpeg vertical render queue]
  → [scheduled autopublish with idempotency] → [metrics sync via official API]
  → [feature store + periodic retrain + eval gate] → [dashboard]
```

- Длинные операции — Celery+Redis, Job lifecycle, восстановление после рестарта.
- Артефакты — S3-совместимое хранилище (MinIO локально), доступ только через `app/infra/s3.py`.
- Метаданные — PostgreSQL (миграции только Alembic).
- Dashboard — React+Vite+Tailwind.

## 5. Стек (фиксированный)

- Backend: FastAPI, SQLAlchemy 2.x (sync), Alembic, Pydantic v2 + pydantic-settings, Celery + Redis, boto3 (только `infra/s3.py`), psycopg v3.
- Media: системные ffmpeg/ffprobe (пути конфигурируемы; запуск только в `services/render/ffmpeg_runner.py`, list-args, без shell), faster-whisper (опц. extra `[whisper]`).
- Frontend: React + Vite + Tailwind, fetch-клиент без лишних библиотек.
- ML (Stage 7): scikit-learn/lightgbm (CPU), joblib (опц. extra `[ml]`).
- Python — через `.venv` в корне репо; Node — только внутри `frontend/`.

## 6. Окружение

Полный перечень env-переменных: `.env.example` (source of truth для имён), парсинг: `backend/app/core/config.py`.
Группы: app, infrastructure (DB/Redis/Celery/S3), security (ENCRYPTION_KEY), upload/clips, ffmpeg, whisper, LLM, AI-веса, платформы, publish-лимиты, ML. Аддитивные расширения env допустимы с фиксацией в CONTRACTS/ARCHITECTURE.

## 7. Stage-объём и Definition of Done (сводка)

| Stage | Объём | Acceptance Gate (кратко) |
|-------|------|--------------------------|
| 0 | Доки, skeleton, /health, DB-модели + Alembic, Celery foundation, S3 abstraction, crypto, frontend skeleton | /health 200; миграции up/down; pytest зелёный без внешних сервисов; frontend build; ауди́т greps чист |
| 1 | Upload+Video, manual Clip, вертикальный render (+runtime verify), выбор платформы, ручная публикация | Все эндпоинты §10 по контрактам; render spec соблюдён (или honest SKIP + моки); pytest зелёный |
| 2 | Локальный text_gen (fake + 1 реальный backend, конфигурируемо) | texts API по CONTRACTS; fake зелёный; CPU fallback покрыт unit |
| 3 | faster-whisper транскрипция, scene detection, эвристический AI-подбор | Цепочка transcribe→scenes→candidates→promote→render→texts на моках/синтетике |
| 4 | Рабочий dashboard | build+tsc; 3 страницы функциональны; нет лендинга/лишних либ |
| 5 | Celery для всех длинных операций + расписание + автопубликация | Ни одна длинная операция не блокирует HTTP; reconcile; защита от дублей |
| 6 | Метрики через официальные API + UI | raw+normalized метрики сохраняются и отображаются |
| 7 | Feature dataset, train/eval/versioning, безопасный ML rerank | dataset gate честен; eval gate; ML с fallback доказан тестами |

Детальные тикеты и DoD — в исходном мастер-промпте (`docs/codex-master-prompt-ai-clipper.md` — предыдущая версия промпта, историческая) и в PROGRESS.md (журнал исполнения).

## 8. Качество и тест-стратегия

- Основной suite: `cd backend && ../../.venv/bin/pytest -m "not real_services"` — без внешних сервисов (SQLite/moto/eager), обязан быть зелёным.
- `tests/integration` — маркер `real_services`, по умолчанию пропускаются (`RUN_REAL_INTEGRATION=1`).
- Реальные проверки окружения — `scripts/verify_*.py` с честными PASS/FAIL/SKIP.
- Запреты (нарушение = провал Stage): hardcoded credentials; boto3 вне `infra/s3.py`; `shell=True`/`os.system`; бинарники/медиа/модели в git; `create_all` в прод-коде.

## 9. Definition of Done всего проекта (Stage 7)

- UC-1..UC-9 проходимы (на моках + real checks где возможно).
- `docs/KNOWLEDGE.md` содержит проверенные URL официальных доков платформ с датами и ограничениями.
- README quickstart: запуск с нуля несколькими командами.
- Все Stage gates пройдены с отчётами §30 в PROGRESS.md.
