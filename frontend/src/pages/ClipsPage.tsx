import { useCallback, useEffect, useState } from "react";
import { ApiError, api, fmtDuration, type Clip, type GeneratedTexts, type Job, type Video } from "../api";

export default function ClipsPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [videoId, setVideoId] = useState<string>("");
  const [clips, setClips] = useState<Clip[]>([]);
  const [form, setForm] = useState({ title: "", start: "0", end: "30" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [texts, setTexts] = useState<Record<string, GeneratedTexts>>({});
  const [assetIds, setAssetIds] = useState<Record<string, string>>({});

  const reloadVideos = useCallback(async () => {
    const page = await api.listVideos();
    setVideos(page.items);
  }, []);

  const reloadClips = useCallback(async () => {
    const page = await api.listClips(videoId || undefined);
    setClips(page.items);
  }, [videoId]);

  useEffect(() => {
    reloadVideos().catch(() => undefined);
  }, [reloadVideos]);

  useEffect(() => {
    reloadClips().catch(() => undefined);
  }, [reloadClips]);

  const createClip = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.createManualClip(videoId, {
        title: form.title || "Без названия",
        start_sec: Number(form.start),
        end_sec: Number(form.end),
      });
      setForm({ title: "", start: "0", end: "30" });
      await reloadClips();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  const pollJob = async (jobId: string, onDone: (job: Job) => void) => {
    const started = Date.now();
    const poll = setInterval(async () => {
      const job = await api.getJob(jobId).catch(() => null);
      if (job && ["succeeded", "failed"].includes(job.status)) {
        clearInterval(poll);
        onDone(job);
      } else if (Date.now() - started > 120_000) {
        clearInterval(poll);
      }
    }, 1200);
  };

  const renderClip = async (clip: Clip) => {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const job = await api.renderClip(clip.id);
      await pollJob(job.id, async (finished) => {
        await reloadClips();
        const assetId = (finished.result as { asset_id?: string } | null)?.asset_id ?? null;
        if (finished.status === "succeeded" && assetId) {
          setAssetIds((prev) => ({ ...prev, [clip.id]: assetId }));
          setNotice(`Рендер клипа «${clip.title}» готов.`);
        } else {
          setNotice(`Рендер не удался: ${finished.error_message ?? "?"}`);
        }
        setBusy(false);
      });
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      setBusy(false);
    }
  };

  const downloadAsset = async (clip: Clip) => {
    const assetId = assetIds[clip.id];
    if (!assetId) {
      setError("Asset id неизвестен в этой сессии — выполните рендер заново.");
      return;
    }
    try {
      const { url } = await api.getRenderUrl(assetId);
      window.open(url, "_blank");
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  };

  const genTexts = async (clip: Clip, platform: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.generateTexts(clip.id, platform);
      setTexts((prev) => ({ ...prev, [`${clip.id}:${platform}`]: result.texts }));
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-lg font-semibold mb-2">Clips</h1>
        <div className="bg-white border border-neutral-200 rounded p-3 space-y-3">
          <div className="flex gap-3 items-center text-sm">
            <label>Видео:</label>
            <select
              value={videoId}
              onChange={(e) => setVideoId(e.target.value)}
              className="border rounded px-2 py-1"
            >
              <option value="">все</option>
              {videos.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.original_filename}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-wrap gap-2 items-end text-sm">
            <label className="flex flex-col">
              <span className="text-neutral-500">Название</span>
              <input
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                className="border rounded px-2 py-1 w-56"
                placeholder="Лучший момент"
              />
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">start, сек</span>
              <input
                value={form.start}
                onChange={(e) => setForm({ ...form, start: e.target.value })}
                className="border rounded px-2 py-1 w-20"
                type="number"
                min="0"
                step="0.1"
              />
            </label>
            <label className="flex flex-col">
              <span className="text-neutral-500">end, сек</span>
              <input
                value={form.end}
                onChange={(e) => setForm({ ...form, end: e.target.value })}
                className="border rounded px-2 py-1 w-20"
                type="number"
                min="0"
                step="0.1"
              />
            </label>
            <button
              onClick={createClip}
              disabled={busy || !videoId}
              className="px-3 py-1.5 bg-neutral-800 text-white rounded hover:bg-neutral-700 disabled:opacity-50"
            >
              Создать клип (5–180с)
            </button>
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          {notice && <p className="text-sm text-neutral-600">{notice}</p>}
        </div>
      </section>

      <section>
        <table className="w-full text-sm bg-white border border-neutral-200 rounded">
          <thead className="bg-neutral-50 text-left text-neutral-500">
            <tr>
              <th className="p-2">Клип</th>
              <th className="p-2">Окно</th>
              <th className="p-2">Длина</th>
              <th className="p-2">Статус</th>
              <th className="p-2">Действия</th>
            </tr>
          </thead>
          <tbody>
            {clips.map((clip) => (
              <tr key={clip.id} className="border-t border-neutral-100 align-top">
                <td className="p-2 font-medium">{clip.title}</td>
                <td className="p-2">
                  {clip.start_sec.toFixed(1)}–{clip.end_sec.toFixed(1)}с
                </td>
                <td className="p-2">{fmtDuration(clip.end_sec - clip.start_sec)}</td>
                <td className="p-2">{clip.status}</td>
                <td className="p-2 space-x-2 whitespace-nowrap">
                  <button onClick={() => renderClip(clip)} disabled={busy} className="text-blue-600 hover:underline disabled:opacity-50">
                    Рендер 1080×1920
                  </button>
                  <button onClick={() => genTexts(clip, "youtube")} disabled={busy} className="text-blue-600 hover:underline disabled:opacity-50">
                    Тексты YT
                  </button>
                  <button onClick={() => genTexts(clip, "tiktok")} disabled={busy} className="text-blue-600 hover:underline disabled:opacity-50">
                    Тексты TT
                  </button>
                  {clip.status === "rendered" && assetIds[clip.id] && (
                    <button onClick={() => downloadAsset(clip)} className="text-blue-600 hover:underline">
                      Скачать
                    </button>
                  )}
                  {texts[`${clip.id}:youtube`] && (
                    <div className="mt-1 text-xs text-neutral-600 max-w-md">
                      <b>YT:</b> {texts[`${clip.id}:youtube`].titles[0]}
                    </div>
                  )}
                  {texts[`${clip.id}:tiktok`] && (
                    <div className="mt-1 text-xs text-neutral-600 max-w-md">
                      <b>TT:</b> {texts[`${clip.id}:tiktok`].titles[0]}{" "}
                      {texts[`${clip.id}:tiktok`].hashtags.slice(0, 4).join(" ")}
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {clips.length === 0 && (
              <tr>
                <td className="p-3 text-neutral-500" colSpan={5}>
                  Клипов нет — создайте вручную или продвигайте кандидата со страницы Videos.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
