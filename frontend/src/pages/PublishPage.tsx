// Publish 2.0: accounts (masked creds), platform limits, publish/schedule with confirm, publications + retry.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  fmtDuration,
  type Clip,
  type PlatformAccount,
  type Publication,
} from "../api";
import { PlusIcon, RefreshIcon, SendIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { EmptyState, ErrorState, Loading } from "../components/ui/Feedback";
import { Field, Select, TextInput, Textarea } from "../components/ui/Field";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useToast } from "../components/ui/Toast";

const PLATFORM_LIMITS: Record<string, string[]> = {
  tiktok: [
    "Непроверенные (unaudited) приложения могут публиковать только в private — укажите SELF_ONLY-режим через «приватный».",
    "Заголовок ≤ 2200 символов; хэштеги 3–8 рекомендованы.",
    "Статус загрузки опрашивается официально (Content Posting API).",
  ],
  youtube: [
    "Проекты без аудита Google — загрузки принудительно private.",
    "Заголовок ≤ 100, описание ≤ 5000, теги суммарно ≤ 500 символов.",
    "Квота 2026: videos.insert — 100 загрузок/день (отдельный бакет).",
  ],
};

function toIso(local: string): string | null {
  if (!local) return null;
  const date = new Date(local);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function NewAccountDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [platform, setPlatform] = useState("tiktok");
  const [externalId, setExternalId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [token, setToken] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createPlatformAccount({
        platform,
        external_account_id: externalId.trim(),
        display_name: displayName.trim() || undefined,
        credentials:
          platform === "youtube"
            ? { refresh_token: token.trim(), client_id: clientId.trim(), client_secret: clientSecret.trim() }
            : { access_token: token.trim() },
      });
      toast.success(`Аккаунт ${platform} добавлен (credentials зашифрованы Fernet)`);
      onCreated();
      onClose();
      setExternalId("");
      setDisplayName("");
      setToken("");
      setClientId("");
      setClientSecret("");
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title="Привязать аккаунт платформы">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label="Платформа" htmlFor="acc-platform">
          <Select id="acc-platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>
            <option value="tiktok">tiktok</option>
            <option value="youtube">youtube</option>
          </Select>
        </Field>
        <Field label="Внешний ID (канал/пользователь)" htmlFor="acc-external" hint="Произвольный идентификатор для ваших ссылок">
          <TextInput id="acc-external" value={externalId} onChange={(e) => setExternalId(e.target.value)} required />
        </Field>
        <Field label="Отображаемое имя" htmlFor="acc-name">
          <TextInput id="acc-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </Field>
        <Field
          label={platform === "youtube" ? "Refresh token (OAuth2)" : "Access token"}
          htmlFor="acc-token"
          hint="Шифруется Fernet и никогда не возвращается из API в открытом виде"
        >
          <TextInput id="acc-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} required autoComplete="off" />
        </Field>
        {platform === "youtube" && (
          <>
            <Field label="Client ID" htmlFor="acc-cid" hint="Можно оставить пустым, если задан YOUTUBE_CLIENT_ID в .env">
              <TextInput id="acc-cid" value={clientId} onChange={(e) => setClientId(e.target.value)} autoComplete="off" />
            </Field>
            <Field label="Client secret" htmlFor="acc-cs" hint="Можно оставить пустым, если задан YOUTUBE_CLIENT_SECRET в .env">
              <TextInput id="acc-cs" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} autoComplete="off" />
            </Field>
          </>
        )}
        {error && (
          <p role="alert" className="text-xs text-red-600">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" loading={busy}>
            Привязать
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function PublishForm({
  clips,
  accounts,
  prefill,
  onDone,
}: {
  clips: Clip[];
  accounts: PlatformAccount[];
  prefill: Partial<Publication> | null;
  onDone: () => void;
}) {
  const renderedClips = clips.filter((c) => c.status === "rendered");
  const [clipId, setClipId] = useState(prefill?.clip_id ?? "");
  const [platform, setPlatform] = useState<string>(prefill?.platform ?? "tiktok");
  const [accountId, setAccountId] = useState(prefill?.platform_account_id ?? "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [privacy, setPrivacy] = useState("public");
  const [scheduleAt, setScheduleAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const toast = useToast();

  useEffect(() => {
    if (prefill?.clip_id) setClipId(prefill.clip_id);
    if (prefill?.platform) setPlatform(prefill.platform);
    if (prefill?.platform_account_id) setAccountId(prefill.platform_account_id);
    const meta = prefill?.metadata as { title?: string; description?: string; privacy?: string } | null;
    if (meta?.title) setTitle(meta.title);
    if (meta?.description) setDescription(meta.description);
    if (meta?.privacy) setPrivacy(meta.privacy);
  }, [prefill]);

  const platformAccounts = accounts.filter((a) => a.platform === platform);
  const selectedClip = clips.find((c) => c.id === clipId);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.manualPublish({
        clip_id: clipId,
        platform,
        platform_account_id: accountId,
        title: title.trim(),
        description: description.trim() || undefined,
        privacy,
        scheduled_at: toIso(scheduleAt) ?? undefined,
      });
      toast.success(
        scheduleAt
          ? `Публикация запланирована на ${new Date(scheduleAt).toLocaleString()}`
          : "Публикация отправлена",
      );
      setConfirmOpen(false);
      setScheduleAt("");
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
      setConfirmOpen(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!clipId || !accountId || !title.trim()) {
          setError("Выберите клип, аккаунт и укажите заголовок");
          return;
        }
        setError(null);
        setConfirmOpen(true);
      }}
      className="flex flex-col gap-3"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Клип (рендер готов)" htmlFor="pub-clip">
          <Select id="pub-clip" value={clipId} onChange={(e) => setClipId(e.target.value)}>
            <option value="">— выберите —</option>
            {renderedClips.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title} ({fmtDuration(c.start_sec)}–{fmtDuration(c.end_sec)})
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Платформа" htmlFor="pub-platform">
          <Select
            id="pub-platform"
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              setAccountId("");
            }}
          >
            <option value="tiktok">tiktok</option>
            <option value="youtube">youtube</option>
          </Select>
        </Field>
        <Field label="Аккаунт" htmlFor="pub-account">
          <Select id="pub-account" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">— выберите —</option>
            {platformAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name ?? a.external_account_id}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Приватность" htmlFor="pub-privacy" hint={PLATFORM_LIMITS[platform]?.[0]}>
          <Select id="pub-privacy" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
            <option value="private">private</option>
            <option value="unlisted">unlisted</option>
            <option value="public">public</option>
          </Select>
        </Field>
      </div>
      <Field label="Заголовок" htmlFor="pub-title" hint={platform === "youtube" ? "до 100 символов" : "до 2200 символов"}>
        <TextInput id="pub-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={platform === "youtube" ? 100 : 2200} />
      </Field>
      <Field label="Описание" htmlFor="pub-desc">
        <Textarea id="pub-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={5000} />
      </Field>
      <Field
        label="Запланировать (необязательно)"
        htmlFor="pub-schedule"
        hint="Пусто — опубликовать сразу. Beat обработает по расписанию с лимитами платформы."
      >
        <TextInput id="pub-schedule" type="datetime-local" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} />
      </Field>
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
      <div>
        <Button type="submit" variant="primary" icon={<SendIcon />} disabled={renderedClips.length === 0}>
          {scheduleAt ? "Запланировать" : "Опубликовать"}
        </Button>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={scheduleAt ? "Подтвердите планирование" : "Подтвердите публикацию"}
        footer={
          <>
            <Button onClick={() => setConfirmOpen(false)}>Отмена</Button>
            <Button variant="primary" loading={busy} onClick={submit}>
              {scheduleAt ? "Запланировать" : "Публиковать"}
            </Button>
          </>
        }
      >
        <p className="text-sm">
          {selectedClip ? `Клип «${selectedClip.title}»` : ""} → <b>{platform}</b>, приватность{" "}
          <b>{privacy}</b>
          {scheduleAt ? `, в ${new Date(scheduleAt).toLocaleString()}` : ", немедленно"}.
        </p>
        <p className="mt-2 text-xs text-neutral-500">
          Реальная отправка пойдёт в платформу через официальный API. Для безопасной проверки
          используйте private/unlisted.
        </p>
      </Dialog>
    </form>
  );
}

export default function PublishPage() {
  const [accounts, setAccounts] = useState<PlatformAccount[] | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [publications, setPublications] = useState<Publication[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [prefill, setPrefill] = useState<Partial<Publication> | null>(null);

  const reload = useCallback(() => {
    api.listPlatformAccounts().then((p) => setAccounts(p.items)).catch(setError);
    api.listClips().then((p) => setClips(p.items)).catch(() => undefined);
    api.listPublications().then((p) => setPublications(p.items)).catch(setError);
  }, []);

  useEffect(reload, [reload]);

  if (error) return <ErrorState error={error} onRetry={reload} context="Публикации" />;
  if (accounts === null || publications === null) return <Loading label="Публикации…" />;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">Публикации</h1>
        <p className="text-sm text-neutral-500">
          Официальные API TikTok и YouTube. Расписание с лимитами, ошибки и повторы.
        </p>
      </div>

      {/* Accounts */}
      <section className="rounded-md border border-neutral-200 bg-white">
        <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-2">
          <h2 className="text-sm font-semibold">Аккаунты платформ</h2>
          <Button size="sm" icon={<PlusIcon />} onClick={() => setDialogOpen(true)}>
            Привязать
          </Button>
        </div>
        <div className="p-3">
          {accounts.length === 0 ? (
            <EmptyState title="Аккаунтов нет" hint="Привяжите TikTok или YouTube аккаунт — токены шифруются." />
          ) : (
            <ul className="divide-y divide-neutral-100">
              {accounts.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                  <StatusBadge status={a.platform} />
                  <span className="font-medium">{a.display_name ?? a.external_account_id}</span>
                  <span className="text-xs text-neutral-500">{a.external_account_id}</span>
                  <span className="rounded border border-neutral-200 bg-neutral-50 px-1.5 py-0.5 font-mono text-xs text-neutral-500">
                    {a.credentials}
                  </span>
                  <span className="ml-auto text-xs text-neutral-500">
                    {a.is_active ? "активен" : "отключён"}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 grid gap-2 text-xs text-neutral-500 sm:grid-cols-2">
            {Object.entries(PLATFORM_LIMITS).map(([platform, limits]) => (
              <div key={platform} className="rounded-md border border-neutral-100 bg-neutral-50 p-2">
                <p className="font-medium text-neutral-700">{platform}</p>
                <ul className="list-inside list-disc">
                  {limits.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Publish form */}
      <section className="rounded-md border border-neutral-200 bg-white">
        <div className="border-b border-neutral-100 px-3 py-2">
          <h2 className="text-sm font-semibold">
            {prefill ? "Повторная публикация (форма предзаполнена)" : "Новая публикация"}
          </h2>
        </div>
        <div className="p-3">
          {clips.filter((c) => c.status === "rendered").length === 0 ? (
            <EmptyState
              title="Нет отрендеренных клипов"
              hint="Сначала отрендерите клип в разделе «Клипы»."
            />
          ) : (
            <>
              {prefill && (
                <div className="mb-2 flex items-center justify-between rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-800">
                  <span>Повтор неудавшейся публикации — параметры взяты из неё.</span>
                  <button
                    onClick={() => setPrefill(null)}
                    className="font-medium underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
                  >
                    Сбросить
                  </button>
                </div>
              )}
              <PublishForm
                clips={clips}
                accounts={accounts}
                prefill={prefill}
                onDone={() => {
                  setPrefill(null);
                  reload();
                }}
              />
            </>
          )}
        </div>
      </section>

      {/* Publications */}
      <section className="rounded-md border border-neutral-200 bg-white">
        <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-2">
          <h2 className="text-sm font-semibold">История публикаций</h2>
          <Button size="sm" icon={<RefreshIcon />} onClick={reload}>
            Обновить
          </Button>
        </div>
        <div className="overflow-x-auto p-3">
          {publications.length === 0 ? (
            <EmptyState title="Публикаций нет" hint="Заполните форму выше." />
          ) : (
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500">
                  <th className="py-1.5 pr-3 font-medium">Статус</th>
                  <th className="py-1.5 pr-3 font-medium">Платформа</th>
                  <th className="py-1.5 pr-3 font-medium">Клип</th>
                  <th className="py-1.5 pr-3 font-medium">Расписание</th>
                  <th className="py-1.5 pr-3 font-medium">Внешний ID</th>
                  <th className="py-1.5 pr-3 font-medium">Попытки</th>
                  <th className="py-1.5 pr-3 font-medium">Действия</th>
                </tr>
              </thead>
              <tbody>
                {publications.map((p) => {
                  const clip = clips.find((c) => c.id === p.clip_id);
                  return (
                    <tr key={p.id} className="border-b border-neutral-100 align-top">
                      <td className="py-1.5 pr-3">
                        <StatusBadge status={p.status} />
                        {p.last_error && (
                          <details className="mt-1 max-w-[16rem] text-xs text-red-600">
                            <summary className="cursor-pointer select-none">Ошибка</summary>
                            <span className="break-words">{p.last_error}</span>
                          </details>
                        )}
                      </td>
                      <td className="py-1.5 pr-3">{p.platform}</td>
                      <td className="max-w-[12rem] truncate py-1.5 pr-3" title={clip?.title ?? p.clip_id}>
                        {clip?.title ?? p.clip_id.slice(0, 8)}
                      </td>
                      <td className="py-1.5 pr-3 text-xs tabular-nums">
                        {p.scheduled_at ? new Date(p.scheduled_at).toLocaleString() : "—"}
                        {p.published_at && (
                          <span className="block text-neutral-500">
                            опубл. {new Date(p.published_at).toLocaleString()}
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 pr-3 font-mono text-xs">{p.external_post_id ?? "—"}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{p.attempt_count}</td>
                      <td className="py-1.5 pr-3">
                        {p.status === "failed" && (
                          <Button size="sm" onClick={() => setPrefill(p)}>
                            Повторить
                          </Button>
                        )}
                        {p.status === "published" && (
                          <Button
                            size="sm"
                            onClick={() =>
                              api
                                .syncMetrics(p.id)
                                .then(() => setPrefill(null))
                                .catch(() => undefined)
                            }
                          >
                            Метрики
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <NewAccountDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={reload}
      />
    </div>
  );
}
