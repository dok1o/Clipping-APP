# KNOWLEDGE — проверенные факты

> Приоритет: MASTER_SPEC > CONTRACTS > ARCHITECTURE > AGENTS > **KNOWLEDGE** > PROGRESS.
> Только проверенные факты с датой и источником. Каждая запись: факт / источник(URL или команда) / дата проверки.

## 1. Окружение песочницы Arena (проверено 2026-09-20)

| Факт | Проверка |
|---|---|
| Python 3.11.2, pip работает, сеть до PyPI есть | `python3 --version`, `pip download fastapi` |
| Node v22.22.3, npm 10.9.8, registry доступен | `node --version`, `npm ping` |
| **ffmpeg/ffprobe ОТСУТСТВУЮТ** | `ffmpeg -version` → command not found |
| Docker/PostgreSQL/Redis/MinIO/GPU отсутствуют | `docker --version` → not found; соединения недоступны |
| `.venv/`, `node_modules/`, `dist/`, `build/` не переживают перезапуск сессии (исключены из снапшота) → кэши пакетов держим в `/home/user/pipcache`, `/home/user/npmcache` | наблюдение платформы |

Следствие: реальный рендер/транскрипция/LLM в песочнице проверяются моками + `scripts/verify_*.py` печатает SKIP; список проверок для реальной машины пользователя — в README §«Проверки на реальной машине».

## 2. Платформы (официальные API)

> Заполняется перед Stage 1.4 после выбора платформы пользователем: актуальные URL официальной документации, дата проверки, квоты/лимиты/аутентификация. Реализация — только по этим документам.

- **Решение (2026-09-20, пользователь): первая платформа — TikTok**; YouTube — вторая, позже.
- TikTok Content Posting API — исследование официальной документации будет выполнено в T1.4 перед реализацией (URL + дата + ограничения будут зафиксированы здесь; реализация только по официальным докам, §0.8).
- YouTube Data API v3 `videos.insert` — исследование отложено до подключения второй платформы.

## 3. Модели и железо (план, требует проверки на реальной машине)

- **faster-whisper**: default `small`, `int8_float16` на GPU, `int8` на CPU; beam 1–5; VAD опц. Память small/int8 ≈ 1GB — влезает в 8GB. Проверить на GPU-машине: `scripts/verify_whisper.py` (Stage 3).
- **Локальный LLM**: квантованная 7–8B instruct (Qwen2.5-7B-Instruct Q4_K_M / Mistral-7B Q4 / Llama-3.1-8B Q4), ~4.5–5.5GB VRAM в Q4. 8GB VRAM → whisper и LLM загружаются ТОЛЬКО последовательно с освобождением памяти (`torch.cuda.empty_cache()`/unload). CPU fallback обязателен (OOM → catch → cpu, фиксировать в Job result `device_used`).
- ML Stage 7: scikit-learn на CPU, артефакты joblib.

## 4. ffmpeg (спецификация рендера)

- Фильтр `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1`; `-ss` до `-i` (быстрый seek) + `-t` после (точная обрезка); `-c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -pix_fmt yuv420p -movflags +faststart -r 30`.
- Проверка на реальной машине: `./.venv/bin/python scripts/verify_ffmpeg.py` (генерирует синтетику `testsrc`+`sine`, рендерит 1с, проверяет выход ffprobe'ом: 1080x1920 / h264 / aac / yuv420p).
- **2026-09-20: реальный рендер подтверждён в песочнице.** ffmpeg 7.0.2-static получен из PyPI-пакета `imageio-ffmpeg` (GitHub egress заблокирован, apt-источники урезаны; FFPROBE отсутствует → duration при загрузке = null, что соответствует спецификации). Прогоны:
  - `FFMPEG_PATH=<imageio-ffmpeg> python scripts/verify_ffmpeg.py` → **RESULT: PASS** (синтетика 1280x720 → рендер 1с → выход 1080x1920 / h264 / aac / yuv420p / faststart moov@36<mdat@2515; probe через fallback-парсер `ffmpeg -i`).
  - `RUN_REAL_INTEGRATION=1 pytest tests/integration` → **1 passed** (e2e: upload настоящего mp4 → clip → render через API+worker → asset ready 1080x1920 → presigned download валидный MP4).
- `imageio-ffmpeg` НЕ входит в зависимости проекта (только удобный способ достать бинаррь в песочнице); на реальной машине — системный ffmpeg/ffprobe.

## 5. Известные ограничения платформенных API (черновик — уточнить при T1.4)

- YouTube Data API v3: квота по умолчанию 10,000 units/day на проект; upload видео ≈ 1600 units; аудитные запросы cheap. (Требует подтверждения официальной документацией.)
- TikTok Content Posting API: доступ к полному posting требует approved app; есть sandbox-окружение. (Требует подтверждения.)

## 6. Решения по инфраструктуре

- Статусы БД — varchar+CHECK (ADR-003), типы переносимые PG/SQLite (ADR-002).
- Celery eager по умолчанию при APP_ENV=test (ADR-013).
- Presigned-URL 900 сек на скачивание рендеров (CONTRACTS §4.9).
