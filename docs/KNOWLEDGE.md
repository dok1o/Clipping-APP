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
- **TikTok Content Posting API — проверено по официальной документации 2026-09-20:**
  - Direct Post: `POST https://open.tiktokapis.com/v2/post/publish/video/init/`, scope `video.publish`; body: `post_info{title, privacy_level, disable_duet, disable_comment, disable_stitch, video_cover_timestamp_ms, is_aigc}` + `source_info{source: FILE_UPLOAD|PULL_FROM_URL, video_size, chunk_size, total_chunk_count | video_url}`; ответ `data.publish_id` (≤64 симв) + `data.upload_url` (только FILE_UPLOAD); успех = `error.code == "ok"`. Источник: https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post (проверено 2026-09-20).
  - Загрузка файла (FILE_UPLOAD): `PUT {upload_url}` (весь URL с query-параметрами), заголовки `Content-Type: video/mp4|video/quicktime|video/webm`, `Content-Length`, `Content-Range: bytes FIRST-LAST/TOTAL`. Источник: там же.
  - Статус: `POST /v2/post/publish/status/fetch/` body `{"publish_id"}` → status ∈ `PROCESSING_UPLOAD | PROCESSING_DOWNLOAD | SEND_TO_USER_INBOX | PUBLISH_COMPLETE | FAILED` (+`fail_reason`); лимит 30 запросов/мин на токен. Источник: https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status (проверено 2026-09-20).
  - Creator info (обязателен перед публикацией по докам): `POST /v2/post/publish/creator_info/query/`, scope video.publish → `privacy_level_options` (публичный аккаунт: PUBLIC_TO_EVERYONE/MUTUAL_FOLLOW_FRIENDS/SELF_ONLY; приватный: FOLLOWER_OF_CREATOR/MUTUAL_FOLLOW_FRIENDS/SELF_ONLY), `comment_disabled/duet_disabled/stitch_disabled`, `max_video_post_duration_sec`. Источник: https://developers.tiktok.com/doc/content-posting-api-reference-query-creator-info (проверено 2026-09-20).
  - Ключевые ограничения: unaudited client → 403 `unaudited_client_can_only_post_to_private_accounts` (посты только приватные до прохождения аудита приложения); PULL_FROM_URL требует верифицированный домен (403 `url_ownership_unverified`); title (caption) — до 2200 симв (по докам/гайдам, проверять на своей интеграции); init rate-limit ~6 запросов/мин на токен; upload_url живёт ~1 час. Sandbox-окружения у TikTok нет — только прод (unaudited = всё приватное).
  - **Наш выбор: FILE_UPLOAD** (наш рендер — локальный файл в MinIO; PULL_FROM_URL требует публичный верифицированный URL, которого у self-hosted нет). Privacy-маппинг: public→PUBLIC_TO_EVERYONE, unlisted→MUTUAL_FOLLOW_FRIENDS, private→SELF_ONLY (у TikTok нет «unlisted»; зафиксировано в CONTRACTS).
- YouTube Data API v3 `videos.insert` — исследование отложено до подключения второй платформы.

## 3. Модели и железо (план, требует проверки на реальной машине)

- **faster-whisper**: default `small`, `int8_float16` на GPU, `int8` на CPU; beam 1–5; VAD опц. Память small/int8 ≈ 1GB — влезает в 8GB. Проверить на GPU-машине: `scripts/verify_whisper.py` (Stage 3).
- **Локальный LLM**: квантованная 7–8B instruct (Qwen2.5-7B-Instruct Q4_K_M / Mistral-7B Q4 / Llama-3.1-8B Q4), ~4.5–5.5GB VRAM в Q4. 8GB VRAM → whisper и LLM загружаются ТОЛЬКО последовательно с освобождением памяти (`torch.cuda.empty_cache()`/unload). CPU fallback обязателен (OOM → catch → cpu, фиксировать в Job result `device_used`).
- ML Stage 7: scikit-learn на CPU, артефакты joblib.
- **2026-09-20 (Stage 2 аудит)**: замер VRAM/времени локальной LLM в песочнице НЕВЫПОЛНИМ (нет GPU, нет ollama, egress только PyPI/npm) — честный SKIP. Проверить на реальной машине: `ollama pull qwen2.5:7b-instruct-q4_K_M` (или mistral:7b / llama3.1:8b Q4), затем POST /api/v1/texts/generate с LLM_BACKEND=ollama; ожидание: Q4 7-8B ≈ 4.5-5.5GB VRAM, Sequential с whisper (не одновременно), CPU fallback покрыт unit-тестом (OOM → num_gpu=0).

## 4. ffmpeg (спецификация рендера)

- **Scene detection (выбор зафиксирован 2026-09-20)**: ffmpeg `select='gt(scene,0.4)',showinfo` с парсингом pts_time из stderr (PySceneDetect отвергнут: тянет OpenCV). Fallback — равномерные окна 30с. **Реальная проверка**: двухсценная синтетика (testsrc→color cut на 4s), `RUN_REAL_INTEGRATION=1 pytest tests/integration` → граница найдена на ~4с (3 passed).
- faster-whisper: модель скачать в песочнице нельзя (huggingface.co и openaipublic.azureedge.net — egress заблокирован, проверено 2026-09-20 curl'ом) → `scripts/verify_whisper.py` даёт честный SKIP; на реальной машине: `pip install -e ".[whisper]"` + `python scripts/verify_whisper.py`.

- Фильтр `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1`; `-ss` до `-i` (быстрый seek) + `-t` после (точная обрезка); `-c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 128k -pix_fmt yuv420p -movflags +faststart -r 30`.
- Проверка на реальной машине: `./.venv/bin/python scripts/verify_ffmpeg.py` (генерирует синтетику `testsrc`+`sine`, рендерит 1с, проверяет выход ffprobe'ом: 1080x1920 / h264 / aac / yuv420p).
- **2026-09-20: реальный рендер подтверждён в песочнице.** ffmpeg 7.0.2-static получен из PyPI-пакета `imageio-ffmpeg` (GitHub egress заблокирован, apt-источники урезаны; FFPROBE отсутствует → duration при загрузке = null, что соответствует спецификации). Прогоны:
  - `FFMPEG_PATH=<imageio-ffmpeg> python scripts/verify_ffmpeg.py` → **RESULT: PASS** (синтетика 1280x720 → рендер 1с → выход 1080x1920 / h264 / aac / yuv420p / faststart moov@36<mdat@2515; probe через fallback-парсер `ffmpeg -i`).
  - `RUN_REAL_INTEGRATION=1 pytest tests/integration` → **1 passed** (e2e: upload настоящего mp4 → clip → render через API+worker → asset ready 1080x1920 → presigned download валидный MP4).
- `imageio-ffmpeg` НЕ входит в зависимости проекта (только удобный способ достать бинаррь в песочнице); на реальной машине — системный ffmpeg/ffprobe.

## 5. Платформенные API — ограничения (проверено по официальным докам)

- **TikTok метрики (проверено 2026-09-20)**: Display API v2 `POST /v2/video/query/?fields=id,view_count,like_count,comment_count,share_count` с body `{"filters": {"video_ids": [...]}}` — ОФИЦИАЛЬНО возвращает счётчики наших постов (scope video.list, user access token). Источники: https://developers.tiktok.com/doc/tiktok-api-v2-video-query (Query Videos) и https://developers.tiktok.com/doc/tiktok-api-v2-video-object (Video Object: view_count int64, like/comment/share int32). Реализовано в `services/analytics/metrics_service.py` (TikTokMetricsAdapter). Research API (более богатые поля) требует аппрува и НЕ используется.
- **TikTok публикация**: см. §2 (quota/audit ограничения, unaudited → приватные посты).
- **YouTube** (вторая платформа, не подключена): метрики будут через YouTube Data API v3 `videos.list(part=statistics)` (официально) и/или YouTube Analytics API — исследование при подключении.

## 6. Решения по инфраструктуре

- Статусы БД — varchar+CHECK (ADR-003), типы переносимые PG/SQLite (ADR-002).
- Celery eager по умолчанию при APP_ENV=test (ADR-013).
- Presigned-URL 900 сек на скачивание рендеров (CONTRACTS §4.9).


## 6. YouTube Data API v3 (проверено по официальным докам 2026-09-21)

- **Загрузка**: `POST https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status` — body `snippet{title≤100, description≤5000, tags (всего ≤500 символов), categoryId}` + `status{privacyStatus: public|unlisted|private, selfDeclaredMadeForKids}`. Ответ инициализации: `200` + заголовок `Location` (URL resumable-сессии); далее `PUT <Location>` с байтами видео (`Content-Type: video/mp4`) → `200/201` + ресурс video с `id`. Реализовано в `services/publish/youtube.py` (raw httpx, single-shot PUT на resumable-сессии — протокольно-корректно для наших размеров; ADR-017). Источники: https://developers.google.com/youtube/v3/docs/videos/insert , https://developers.google.com/youtube/v3/guides/uploading_a_video .
- **OAuth2**: refresh-flow `POST https://oauth2.googleapis.com/token` (form: grant_type=refresh_token, refresh_token, client_id, client_secret). Прямой `access_token` в credentials тоже поддержан. Источник: https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps .
- **КВОТЫ (обновление 2026! Last updated 2026-09-15)**: у `videos.insert` СВОЙ бакет — **100 загрузок/день** (1 квота за вызов), у `search.list` — 100/день, прочие методы — суммарно 10 000 юнитов/день; сброс в полночь PT. Старые блоги про «1600 юнитов за загрузку» устарели. Есть сообщения о скрытом лимите 'Video Uploads per day' → HTTP 429 (googleapis/google-api-python-client#2753, май 2026). Источник: https://developers.google.com/youtube/v3/determine_quota_cost .
- **Неверифицированные проекты**: загрузки через API из проектов без аудита (созданных после 2020-07-28) принудительно приватные — аналог TikTok unaudited. Источник: https://developers.google.com/youtube/v3/docs/videos/insert .
- **Метрики**: `GET https://www.googleapis.com/youtube/v3/videos?part=statistics&id={id}` (1 юнит) → `items[].statistics{viewCount, likeCount, commentCount}` (строки); счётчика shares НЕТ (остаётся None). Реализовано `YouTubeMetricsAdapter`. Источники: https://developers.google.com/youtube/v3/docs/videos/list , https://developers.google.com/youtube/v3/docs/video .
- **Shorts**: вертикальные видео ≤3 мин распознаются как Shorts автоматически, отдельного API-флага нет (официального эндпоинта «shorts» не существует).

## 7. Whop Content Rewards (проверено по официальным страницам 2026-09-22)

- **Продукт**: Content Rewards — кампании брендов для креаторов (clipping / music / logo / UGC). Креатор постит со своих аккаунтов и отправляет ссылку. Источник: https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/creators (официальная creator-страница, проверена 2026-09-22).
- **Модели выплат** (FAQ, та же страница): CPM (за 1000 просмотров), per post (флэт за одобренный пост), retainer (фикс за цикл за согласованные deliverables — pro rata или только при полном выполнении). Тип кампании виден на странице кампании.
- **Окно отправки**: опубликованную ссылку нужно отправить **в течение 30 минут** после поста («Post to the platform the campaign asks for, then submit the link within 30 minutes»).
- **Причины отказов** (FAQ): wrong platform, missing tags or disclosure, reused content, post edited/deleted после отправки; причина указывается в rejection note.
- **Тайминг выплат CPM** (FAQ): клип зарабатывает **7 дней с момента approval**, затем payout держится на **3-дневном hold**. Per-post/retainer зависят от настроек кампании.
- **Creator fee** (проверено по двум официальным страницам 2026-09-22: FAQ https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/creators и pricing https://b4e0vdqv6zgqeqj4pfgm.apps.whop.com/pricing/creators): **CPM — всегда плоские 10%**; **per-post и retainer с бюджетом ≥ $5,000 — 0%** (creator keeps 100%). Это именно creator fee — НЕ смешивать с brand/platform fee (отдельная сетка для брендов). Нюанс с pricing-страницы: колонка «0%» помечена «Verified» — при импорте кампании порог/условие подтверждается пользователем как term. Вывод средств — без комиссий и без минимума.
- **Потолок**: каждая кампания задаёт max payout за один клип — клип перестаёт зарабатывать по достижении потолка. Также бывает min payout (порог попадания в review).
- **Вывод**: кошелёк, без минимума и без комиссии за вывод.
- **Платформы кампаний**: TikTok, YouTube, Instagram, X (иконки на creator-странице).
- **ВАЖНО (provider, формулировка по ревью 2026-09-22)**: официальный creator API для Content Rewards **не найден на дату проверки 2026-09-22**. Ревизия индекса https://docs.whop.com/llms.txt выполнена **частично** (выборочные чанки из 32; полная ревизия — обязательное условие перед автоматизацией CR-4). Индекс документирует payments/memberships/chat/reviews/shipments/app-builds и отдельный **Bounties API** — Bounties ≠ Content Rewards, не путать. Официальная страница https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards описывает Content Rewards как brand-side инструмент. Сторонние скраперы (Apify и т.п.) ЗАПРЕЩЕНЫ правилами проекта. Вывод: **CR-4 начинается с manual provider** (открыть форму, подготовить URL/checklist/countdown); автоматический adapter — только при обнаружении и проверке официального документированного API.
- **Все числа (30 мин / 7 дней / 3 дня / 10% / $5k) — изменчивые правила**: хранить как versioned campaign terms при импорте кампании с подтверждением пользователя, НЕ как hardcoded truth.

## 8. Instagram Platform — официальная публикация Reels (проверено 2026-09-22)

- **Кто может**: только Professional accounts (Business/Creator), привязанные к Facebook Page. Personal accounts — нет. Источник: https://developers.facebook.com/docs/instagram-platform/content-publishing .
- **Протокол (2 шага + poll)**: `POST /{ig-user-id}/media` с `media_type=REELS`, `video_url` (ОБЯЗАТЕЛЬНО публичный URL — Meta сам скачивает файл), `caption`, опции `share_to_feed`, `cover_url`, `thumb_offset`, `audio_name` → контейнер; `GET /{container-id}?fields=status_code` poll до `FINISHED` (значения IN_PROGRESS/FINISHED/ERROR/EXPIRED); затем `POST /{ig-user-id}/media_publish` с `creation_id` → IG Media ID. Источник: https://developers.facebook.com/docs/instagram-platform/content-publishing/ и https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/ .
- **Лимиты**: `GET /{ig-user-id}/content_publishing_limit` — текущее использование publishing rate limit; Reels через API у большинства аккаунтов ≤90 сек; видео должно соответствовать Reels-спецификациям.
- **Также существует** resumable upload через `https://rupload.facebook.com/ig-api-upload/` (для больших видео).
- **Разрешения и доступ** (проверено по официальной доке 2026-09-22, Updated: Jun 30, 2026 — https://developers.facebook.com/documentation/instagram-platform/content-publishing ): **Instagram API with Instagram Login**: `instagram_business_basic` + `instagram_business_content_publish`, host `graph.instagram.com`, Instagram User token, Business Login for Instagram. **Instagram API with Facebook Login**: `instagram_basic` + `instagram_content_publish` + `pages_read_engagement` (+ `ads_management`/`ads_read` при выдаче роли через Business Manager), host `graph.facebook.com` (+ rupload для resumable), Facebook Page token, Facebook Login for Business. Требуется Access Level (Advanced Access = App Review) и учёт Page Publishing Authorization (PPA). **Rate limit: 100 API-публикованных постов за скользящие 24ч** (enforced на `media_publish`); текущее использование — `GET /{ig-user-id}/content_publishing_limit`. Resumable upload (`upload_type=resumable`) — только для Facebook Login for Business. Без прав/без публичного media URL — ручной fallback (правило CR-4).
- **Для adapter**: учёт container flow, статуса обработки (status_code), ограничений media delivery (публичный video_url — наш presigned S3 URL подходит, но URL должен быть доступен Meta). Метрики — официальные insights endpoints.
