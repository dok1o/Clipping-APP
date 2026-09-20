import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Clip, type PlatformAccount, type Publication } from "../api";

export default function PublishPage() {
  const [clips, setClips] = useState<Clip[]>([]);
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [publications, setPublications] = useState<Publication[]>([]);
  const [form, setForm] = useState({
    clip_id: "",
    platform: "tiktok",
    platform_account_id: "",
    title: "",
    description: "",
    privacy: "public",
  });
  const [accountForm, setAccountForm] = useState({
    platform: "tiktok",
    external_account_id: "",
    display_name: "",
    access_token: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const [cl, acc, pubs] = await Promise.all([
      api.listClips(),
      api.listPlatformAccounts(),
      api.listPublications(),
    ]);
    setClips(cl.items);
    setAccounts(acc.items);
    setPublications(pubs.items);
  }, []);

  useEffect(() => {
    reload().catch((e) => setError(String(e)));
  }, [reload]);

  const createAccount = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.createPlatformAccount({
        platform: accountForm.platform,
        external_account_id: accountForm.external_account_id,
        display_name: accountForm.display_name || undefined,
        credentials: { access_token: accountForm.access_token },
        scopes: ["video.publish"],
      });
      setAccountForm({ platform: "tiktok", external_account_id: "", display_name: "", access_token: "" });
      setNotice("Аккаунт добавлен (токен зашифрован).");
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  const publish = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const publication = await api.manualPublish({
        clip_id: form.clip_id,
        platform: form.platform,
        platform_account_id: form.platform_account_id,
        title: form.title,
        description: form.description || undefined,
        privacy: form.privacy,
      });
      setNotice(
        `Публикация ${publication.status}${publication.external_post_id ? ` (id: ${publication.external_post_id})` : ""}`,
      );
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  const renderedClips = clips.filter((c) => c.status === "rendered");

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-lg font-semibold mb-2">Publish</h1>

        <div className="bg-white border border-neutral-200 rounded p-3 space-y-3">
          <h2 className="font-medium text-sm">Платформенный аккаунт (TikTok)</h2>
          <div className="flex flex-wrap gap-2 text-sm items-end">
            <label className="flex flex-col">
              <span className="text-neutral-500">Платформа</span>
              <select
                value={accountForm.platform}
                onChange={(e) => setAccountForm({ ...accountForm, platform: e.target.value })}
                className="border rounded px-2 py-1"
              >
                <option value="tiktok">tiktok</option>
                <option value="youtube">youtube</option>
              </select>
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">external_account_id</span>
              <input
                value={accountForm.external_account_id}
                onChange={(e) => setAccountForm({ ...accountForm, external_account_id: e.target.value })}
                className="border rounded px-2 py-1 w-48"
              />
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">Имя (опц.)</span>
              <input
                value={accountForm.display_name}
                onChange={(e) => setAccountForm({ ...accountForm, display_name: e.target.value })}
                className="border rounded px-2 py-1 w-40"
              />
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">access_token</span>
              <input
                value={accountForm.access_token}
                onChange={(e) => setAccountForm({ ...accountForm, access_token: e.target.value })}
                className="border rounded px-2 py-1 w-64"
                type="password"
              />
            </label>
            <button
              onClick={createAccount}
              disabled={busy || !accountForm.external_account_id || !accountForm.access_token}
              className="px-3 py-1.5 border rounded hover:bg-neutral-50 disabled:opacity-50"
            >
              Добавить (Fernet)
            </button>
          </div>
          {accounts.length > 0 && (
            <p className="text-xs text-neutral-500">
              Аккаунты: {accounts.map((a) => `${a.platform}:${a.external_account_id} (${a.credentials})`).join(", ")}
            </p>
          )}
        </div>

        <div className="bg-white border border-neutral-200 rounded p-3 space-y-3 mt-3">
          <h2 className="font-medium text-sm">Ручная публикация</h2>
          <div className="flex flex-wrap gap-2 text-sm items-end">
            <label className="flex flex-col">
              <span className="text-neutral-500">Клип (rendered)</span>
              <select
                value={form.clip_id}
                onChange={(e) => setForm({ ...form, clip_id: e.target.value })}
                className="border rounded px-2 py-1 w-56"
              >
                <option value="">— выбрать —</option>
                {renderedClips.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title} ({c.start_sec.toFixed(0)}–{c.end_sec.toFixed(0)}с)
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">Платформа</span>
              <select
                value={form.platform}
                onChange={(e) => setForm({ ...form, platform: e.target.value })}
                className="border rounded px-2 py-1"
              >
                <option value="tiktok">tiktok</option>
                <option value="youtube">youtube</option>
              </select>
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">Аккаунт</span>
              <select
                value={form.platform_account_id}
                onChange={(e) => setForm({ ...form, platform_account_id: e.target.value })}
                className="border rounded px-2 py-1 w-48"
              >
                <option value="">— выбрать —</option>
                {accounts
                  .filter((a) => a.platform === form.platform)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.external_account_id}
                    </option>
                  ))}
              </select>
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">privacy</span>
              <select
                value={form.privacy}
                onChange={(e) => setForm({ ...form, privacy: e.target.value })}
                className="border rounded px-2 py-1"
              >
                <option value="public">public</option>
                <option value="unlisted">unlisted</option>
                <option value="private">private</option>
              </select>
            </label>
          </div>
          <div className="flex flex-col gap-2 text-sm">
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="border rounded px-2 py-1"
              placeholder="Заголовок / caption"
            />
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="border rounded px-2 py-1"
              placeholder="Описание (опционально)"
              rows={2}
            />
          </div>
          <button
            onClick={publish}
            disabled={busy || !form.clip_id || !form.platform_account_id || !form.title}
            className="px-3 py-1.5 bg-neutral-800 text-white rounded hover:bg-neutral-700 disabled:opacity-50"
          >
            Опубликовать
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {notice && <p className="text-sm text-neutral-600">{notice}</p>}
        </div>
      </section>

      <section>
        <h2 className="font-medium mb-2">Публикации</h2>
        <table className="w-full text-sm bg-white border border-neutral-200 rounded">
          <thead className="bg-neutral-50 text-left text-neutral-500">
            <tr>
              <th className="p-2">Клип</th>
              <th className="p-2">Платформа</th>
              <th className="p-2">Статус</th>
              <th className="p-2">external id</th>
              <th className="p-2">Ошибка</th>
              <th className="p-2">Создана</th>
            </tr>
          </thead>
          <tbody>
            {publications.map((p) => {
              const clip = clips.find((c) => c.id === p.clip_id);
              return (
                <tr key={p.id} className="border-t border-neutral-100">
                  <td className="p-2">{clip?.title ?? p.clip_id.slice(0, 8)}</td>
                  <td className="p-2">{p.platform}</td>
                  <td className="p-2">{p.status}</td>
                  <td className="p-2">{p.external_post_id ?? "—"}</td>
                  <td className="p-2 text-red-600 max-w-xs truncate">{p.last_error ?? ""}</td>
                  <td className="p-2 text-neutral-500">{new Date(p.created_at).toLocaleString()}</td>
                </tr>
              );
            })}
            {publications.length === 0 && (
              <tr>
                <td className="p-3 text-neutral-500" colSpan={6}>
                  Публикаций пока нет.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
