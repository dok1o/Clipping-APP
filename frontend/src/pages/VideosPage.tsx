import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, fmtBytes, fmtDuration, type Candidate, type TranscriptSegment, type Video } from "../api";

export default function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Video | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[] | null>(null);
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [rankedBy, setRankedBy] = useState<string>("heuristic");
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    const page = await api.listVideos();
    setVideos(page.items);
  }, []);

  useEffect(() => {
    reload().catch((e) => setUploadError(String(e)));
  }, [reload]);

  const upload = async () => {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setUploadError(null);
    try {
      await api.uploadVideo(file);
      fileInput.current && (fileInput.current.value = "");
      await reload();
    } catch (e) {
      setUploadError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  const openVideo = async (video: Video) => {
    setSelected(video);
    setTranscript(null);
    setCandidates(null);
    try {
      const [tr, cd] = await Promise.all([
        api.getTranscript(video.id),
        api.listCandidates(video.id),
      ]);
      setTranscript(tr.items);
      setCandidates(cd.items);
    } catch {
      setTranscript(null);
    }
  };

  const transcribe = async () => {
    if (!selected) return;
    setBusy(true);
    setNotice(null);
    try {
      await api.transcribe(selected.id);
      setNotice("Транскрипция запущена (job). Обновите детали через несколько секунд.");
      const started = Date.now();
      const poll = setInterval(async () => {
        const tr = await api.getTranscript(selected.id).catch(() => null);
        if (tr && tr.total > 0) {
          setTranscript(tr.items);
          clearInterval(poll);
          setBusy(false);
        } else if (Date.now() - started > 60_000) {
          clearInterval(poll);
          setBusy(false);
        }
      }, 1500);
    } catch (e) {
      setNotice(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
      setBusy(false);
    }
  };

  const genCandidates = async () => {
    if (!selected) return;
    setBusy(true);
    setNotice(null);
    try {
      const page = await api.generateCandidates(selected.id, 5);
      setRankedBy(page.ranked_by);
      setCandidates(page.items);
    } catch (e) {
      setNotice(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  const promote = async (candidate: Candidate) => {
    setBusy(true);
    try {
      const clip = await api.promoteCandidate(candidate.id);
      setNotice(`Кандидат ${candidate.start.toFixed(0)}-${candidate.end.toFixed(0)}с → клип «${clip.title}» (draft). Смотрите на странице Clips.`);
    } catch (e) {
      setNotice(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-lg font-semibold mb-2">Videos</h1>
        <div className="flex items-center gap-3 bg-white border border-neutral-200 rounded p-3">
          <input ref={fileInput} type="file" accept=".mp4,.mov,.webm,.mkv" className="text-sm" />
          <button
            onClick={upload}
            disabled={busy}
            className="px-3 py-1.5 bg-neutral-800 text-white rounded text-sm hover:bg-neutral-700 disabled:opacity-50"
          >
            {busy ? "…" : "Загрузить"}
          </button>
          <span className="text-xs text-neutral-500">mp4 / mov / webm / mkv, до 1024 MB</span>
        </div>
        {uploadError && <p className="mt-2 text-sm text-red-600">{uploadError}</p>}
      </section>

      <section>
        <table className="w-full text-sm bg-white border border-neutral-200 rounded">
          <thead className="bg-neutral-50 text-left text-neutral-500">
            <tr>
              <th className="p-2">Файл</th>
              <th className="p-2">Статус</th>
              <th className="p-2">Длина</th>
              <th className="p-2">Размер</th>
              <th className="p-2">Загружен</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {videos.map((v) => (
              <tr key={v.id} className="border-t border-neutral-100">
                <td className="p-2 font-medium">{v.original_filename}</td>
                <td className="p-2">{v.status}</td>
                <td className="p-2">{fmtDuration(v.duration_sec)}</td>
                <td className="p-2">{fmtBytes(v.size_bytes)}</td>
                <td className="p-2 text-neutral-500">{new Date(v.created_at).toLocaleString()}</td>
                <td className="p-2">
                  <button onClick={() => openVideo(v)} className="text-blue-600 hover:underline">
                    Детали
                  </button>
                </td>
              </tr>
            ))}
            {videos.length === 0 && (
              <tr>
                <td className="p-3 text-neutral-500" colSpan={6}>
                  Нет видео — загрузите первый файл.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {selected && (
        <section className="bg-white border border-neutral-200 rounded p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{selected.original_filename}</h2>
            <div className="flex gap-2">
              <button onClick={transcribe} disabled={busy} className="px-3 py-1 border rounded text-sm hover:bg-neutral-50 disabled:opacity-50">
                Транскрибировать
              </button>
              <button onClick={genCandidates} disabled={busy} className="px-3 py-1 border rounded text-sm hover:bg-neutral-50 disabled:opacity-50">
                AI-кандидаты (top 5)
              </button>
            </div>
          </div>
          {notice && <p className="text-sm text-neutral-600">{notice}</p>}

          {transcript && transcript.length > 0 && (
            <details>
              <summary className="text-sm cursor-pointer">Транскрипт ({transcript.length} сегментов)</summary>
              <div className="mt-2 max-h-48 overflow-y-auto text-sm space-y-1">
                {transcript.map((s) => (
                  <div key={s.id} className="flex gap-2">
                    <span className="text-neutral-400 w-20 shrink-0">
                      {s.start.toFixed(1)}–{s.end.toFixed(1)}
                    </span>
                    <span>{s.text}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {candidates && candidates.length > 0 && (
            <div>
              <h3 className="text-sm font-medium mb-1">
                Кандидаты
                <span
                  className={
                    "ml-2 px-1.5 py-0.5 rounded text-xs " +
                    (rankedBy === "ml"
                      ? "bg-blue-100 text-blue-700"
                      : "bg-neutral-100 text-neutral-500")
                  }
                  title={
                    rankedBy === "ml"
                      ? "ML-ранжирование (активная модель)"
                      : "Эвристика (ML-модель не активна)"
                  }
                >
                  {rankedBy === "ml" ? "ML-rerank" : "эвристика"}
                </span>
              </h3>
              <table className="w-full text-sm">
                <tbody>
                  {candidates.map((c) => (
                    <tr key={c.id} className="border-t border-neutral-100">
                      <td className="p-1.5 w-24">{c.start.toFixed(0)}–{c.end.toFixed(0)}с</td>
                      <td className="p-1.5 w-16">score {c.score.toFixed(2)}</td>
                      <td className="p-1.5 text-neutral-500">{c.reason}</td>
                      <td className="p-1.5 w-24 text-right">
                        <button onClick={() => promote(c)} className="text-blue-600 hover:underline">
                          → клип
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
