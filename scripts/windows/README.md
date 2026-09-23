# Windows launcher

Машина пользователя — Windows. Скрипты запускают весь локальный стек и не требуют ручного ввода команд.

```powershell
# из корня репозитория
powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1 -All      # API + worker + beat + frontend
powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1           # только API (eager-режим без Redis)
powershell -ExecutionPolicy Bypass -File scripts\windows\health.ps1          # /health + статусы процессов
powershell -ExecutionPolicy Bypass -File scripts\windows\stop.ps1            # остановка
```

Требования: Python 3.11+ и Node 20+ на PATH; `.env` в корне (из `.env.example`) — подхватывается автоматически.
PID-файлы пишутся в `.run/` (вне git). `worker`/`beat` требуют живой Redis (`REDIS_URL`); без него используйте
запуск только API — Celery работает в eager-режиме (`CELERY_TASK_ALWAYS_EAGER=1` в `.env`).

Скрипты написаны по фактической структуре репо и проверены синтаксически; живая проверка выполняется
на Windows-машине пользователя (в Linux-песочнице PowerShell отсутствует — честный SKIP, см. PROGRESS Stage 9).
