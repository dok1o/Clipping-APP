// Videos: upload (dnd + progress + client validation), list, transcript, candidates, manual clips.
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  fmtBytes,
  fmtDuration,
  uploadVideoWithProgress,
  type Candidate,
  type Clip,
  type TranscriptSegment,
  type Video,
} from "../api";
import { ScissorsIcon, SparkIcon, UploadIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, Loading, Progress } from "../components/ui/Feedback";
import { Field, TextInput } from "../components/ui/Field";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useToast } from "../components/ui/Toast";
import { useJobWait } from "../hooks/useJobWait";
import { usePolling } from "../hooks/usePolling";

const ALLOWED_EXT = [".mp4", ".mov", ".webm", ".mkv"];
const MAX_SIZE = 2 * 1024 * 1024 * 1024; // 2 GB sanity cap

function UploadZone({ onUploaded }: { onUploaded: (v: Video) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  const validate = (file: File): string | null => {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXT.includes(ext)) {
      return `Формат ${ext || "без расширения"} не поддерживается. Разрешены: ${ALLOWED_EXT.join(", ")}`;
    }
    if (file.size > MAX_SIZE) return `Файл больше 2 ГБ (${fmtBytes(file.size)})`;
    return null;
  };

  const start = async (file: File) => {
    const problem = validate(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setProgress(0);
    try {
      const video = await uploadVideoWithProgress(file, setProgress);
      toast.success(`Видео «${video.original_filename}» загружено`);
      onUploaded(video);
    } catch (e) {
      const message = e instanceof ApiError ? `${e.code}: ${e.message}` : String(e);
      setError(message);
      toast.error("Загрузка не удалась");
    } finally {
      setProgress(null);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div
        role="button"
        tabIndex={0}
        aria-label="Загрузить видео (перетащите файл или нажмите)"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void start(file);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-md border-2 border-dashed px-4 py-8 text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
          dragOver ? "border-blue-400 bg-blue-50" : "border-neutral-300 bg-white hover:bg-neutral-50"
        }`}
      >
        <span className="text-neutral-500">
          <UploadIcon width={24} height={24} />
        </span>
        <p className="text-sm font-medium text-neutral-700">
          Перетащите видео сюда или нажмите для выбора
        </p>
        <p className="text-xs text-neutral-500">MP4, MOV, WebM, MKV · до 2 ГБ</p>
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_EXT.join(",")}
          className="hidden"
          aria-hidden="true"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void start(file);
            e.target.value = "";
          }}
        />
      </div>
      {progress !== null && (
        <div className="flex flex-col gap-1">
          <Progress value={progress * 100} label="Загрузка файла" />
          <p className="text-xs text-neutral-500 tabular-nums">
            Загрузка… {Math.round(progress * 100)}%
          </p>
        </div>
      )}
      {error && <ErrorState error={new Error(error)} context="Загрузка файла" />}
    </div>
  );
}

function TranscriptBlock({ videoId }: { videoId: string }) {
  const [segments, setSegments] = useState<TranscriptSegment[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(() => {
    api
      .getTranscript(videoId)
      .then((page) => {
        setSegments(page.items);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 409) setSegments([]);
        else setError(e);
      });
  }, [videoId]);

  useEffect(load, [load]);
  if (error) return <ErrorState error={error} onRetry={load} context="Транскрипт" />;
  if (segments === null) return <Loading label="Транскрипт…" />;

  if (segments.length === 0) {
    return (
      <p className="text-sm text-neutral-500">
        Транскрипта нет — запустите транскрипцию (faster-whisper) выше.
      </p>
    );
  }
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-sm font-medium text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        {open ? "Скрыть" : "Показать"} транскрипт ({segments.length} сегментов)
      </button>
      {open && (
        <div className="mt-2 max-h-64 overflow-y-auto rounded-md border border-neutral-200 bg-white">
          <ul className="divide-y divide-neutral-100">
            {segments.map((s) => (
              <li key={s.id} className="flex gap-3 px-3 py-1.5 text-sm">
                <span className="w-20 shrink-0 pt-0.5 text-xs tabular-nums text-neutral-500">
                  {fmtDuration(s.start)}–{fmtDuration(s.end)}
                </span>
                <span className="min-w-0">{s.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ManualClipForm({ videoId, onCreated }: { videoId: string; onCreated: (c: Clip) => void }) {
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("15");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const s = Number(start);
    const t = Number(end);
    if (!Number.isFinite(s) || !Number.isFinite(t) || t <= s) {
      setError("Конец должен быть больше начала");
      return;
    }
    if (t - s < 5) {
      setError("Минимальная длительность клипа — 5 секунд");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const clip = await api.createManualClip(videoId, {
        title: title.trim() || `Клип ${s.toFixed(0)}–${t.toFixed(0)}с`,
        start_sec: s,
        end_sec: t,
      });
      onCreated(clip);
      setTitle("");
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_5rem_5rem_auto] sm:items-end">
        <Field label="Название" htmlFor="clip-title">
          <TextInput
            id="clip-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Например: Главная мысль"
            maxLength={140}
          />
        </Field>
        <Field label="Начало, с" htmlFor="clip-start">
          <TextInput
            id="clip-start"
            type="number"
            min={0}
            step={0.1}
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </Field>
        <Field label="Конец, с" htmlFor="clip-end">
          <TextInput
            id="clip-end"
            type="number"
            min={0}
            step={0.1}
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </Field>
        <Button type="submit" variant="primary" loading={busy} icon={<ScissorsIcon />}>
          Клип
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-red-600">
          {error}
        </p>
      )}
    </form>
  );
}

function VideoDetail({ video, onClipCreated }: { video: Video; onClipCreated: (c: Clip) => void }) {
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [rankedBy, setRankedBy] = useState("heuristic");
  const [genBusy, setGenBusy] = useState(false);
  const [genError, setGenError] = useState<unknown>(null);
  const toast = useToast();
  const transcribe = useJobWait();
  const navigate = useNavigate();

  const loadCandidates = useCallback(() => {
    api
      .listCandidates(video.id)
      .then((page) => {
        setCandidates(page.items);
        setRankedBy(page.ranked_by);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 409) setCandidates([]);
        else setGenError(e);
      });
  }, [video.id]);

  useEffect(loadCandidates, [loadCandidates]);

  const startTranscribe = async () => {
    try {
      const { job_id } = await api.transcribe(video.id);
      transcribe.wait(job_id);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Не удалось запустить транскрипцию");
    }
  };

  const generate = async () => {
    setGenBusy(true);
    setGenError(null);
    try {
      const page = await api.generateCandidates(video.id, 5);
      setCandidates(page.items);
      setRankedBy(page.ranked_by);
      toast.success(`Кандидаты сгенерированы (${page.ranked_by === "ml" ? "ML-rerank" : "эвристика"})`);
    } catch (e) {
      setGenError(e);
      toast.error("Генерация кандидатов не удалась");
    } finally {
      setGenBusy(false);
    }
  };

  const promote = async (candidate: Candidate) => {
    try {
      const clip = await api.promoteCandidate(candidate.id);
      toast.success(`Клип «${clip.title}» создан`);
      onClipCreated(clip);
      navigate("/clips");
    } catch (e) {
      toast.error(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-md border border-neutral-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold" title={video.original_filename}>
            {video.original_filename}
          </h2>
          <p className="text-xs text-neutral-500">
            {fmtDuration(video.duration_sec)} · {fmtBytes(video.size_bytes)} ·{" "}
            {video.width && video.height ? `${video.width}×${video.height}` : "размер неизвестен"} ·{" "}
            {new Date(video.created_at).toLocaleString()}
          </p>
        </div>
        <StatusBadge status={video.status} />
      </div>
      {video.error_message && (
        <ErrorState error={new Error(video.error_message)} context="Видео" />
      )}

      {/* Transcription */}
      <div className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-medium">Транскрипция</h3>
          <Button size="sm" onClick={startTranscribe} disabled={transcribe.running}>
            {transcribe.job && transcribe.running ? "Транскрибация…" : "Запустить"}
          </Button>
          {transcribe.job && (
            <StatusBadge status={transcribe.job.status} title={transcribe.job.error_message ?? ""} />
          )}
          {transcribe.error ? (
            <ErrorState error={transcribe.error} context="Job транскрипции" />
          ) : null}
        </div>
        <TranscriptBlock videoId={video.id} />
      </div>

      {/* Candidates */}
      <div className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="flex items-center gap-1.5 text-sm font-medium">
            Кандидаты
            <span
              className={`rounded border px-1.5 py-0.5 text-xs ${
                rankedBy === "ml"
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-neutral-200 bg-neutral-100 text-neutral-500"
              }`}
              title={
                rankedBy === "ml"
                  ? "ML-ранжирование (активная модель)"
                  : "Эвристика (ML-модель не активна)"
              }
            >
              {rankedBy === "ml" ? "ML-rerank" : "эвристика"}
            </span>
          </h3>
          <Button
            size="sm"
            onClick={generate}
            loading={genBusy}
            disabled={video.status !== "ready"}
            icon={<SparkIcon />}
          >
            Подобрать моменты
          </Button>
        </div>
        {genError ? (
          <ErrorState error={genError} onRetry={generate} context="Кандидаты" />
        ) : null}
        {candidates === null && !genError && <Loading label="Кандидаты…" />}
        {candidates !== null && candidates.length === 0 && (
          <EmptyState
            title="Кандидатов нет"
            hint="Сначала транскрибируйте видео, затем запустите подбор моментов."
          />
        )}
        {candidates !== null && candidates.length > 0 && (
          <ul className="divide-y divide-neutral-100 rounded-md border border-neutral-200">
            {candidates.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                <span className="w-24 shrink-0 tabular-nums text-neutral-600">
                  {fmtDuration(c.start)}–{fmtDuration(c.end)}
                </span>
                <span className="w-16 shrink-0 tabular-nums font-medium">{c.score.toFixed(2)}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-neutral-500" title={c.reason}>
                  {c.reason}
                </span>
                <Button size="sm" variant="primary" onClick={() => promote(c)}>
                  → клип
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Manual clip */}
      <div className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
        <h3 className="text-sm font-medium">Ручной клип</h3>
        <ManualClipForm videoId={video.id} onCreated={onClipCreated} />
      </div>
    </div>
  );
}

export default function VideosPage() {
  const { videoId } = useParams();
  const [videos, setVideos] = useState<Video[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [selectedId, setSelectedId] = useState<string | null>(videoId ?? null);

  const reload = useCallback(() => {
    api
      .listVideos(100)
      .then((page) => setVideos(page.items))
      .catch(setError);
  }, []);

  useEffect(reload, [reload]);
  usePolling(reload, 10000);

  useEffect(() => {
    if (videoId) setSelectedId(videoId);
  }, [videoId]);

  if (error) return <ErrorState error={error} onRetry={reload} context="Список видео" />;
  if (videos === null) return <Loading label="Видео…" />;

  const selected = videos.find((v) => v.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold">Видео</h1>
        <p className="text-sm text-neutral-500">
          Загрузите длинное видео — дальше транскрипция, подбор моментов и клипы.
        </p>
      </div>

      <UploadZone
        onUploaded={() => {
          reload();
          toastNoop();
        }}
      />

      {videos.length === 0 ? (
        <EmptyState
          title="Видео пока не загружены"
          hint="Перетащите MP4/MOV/WebM/MKV в зону загрузки выше."
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(280px,380px)_1fr]">
          <ul className="flex flex-col divide-y divide-neutral-100 rounded-md border border-neutral-200 bg-white">
            {videos.map((v) => (
              <li key={v.id}>
                <button
                  onClick={() => setSelectedId(v.id)}
                  aria-current={v.id === selectedId}
                  className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm hover:bg-neutral-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 ${
                    v.id === selectedId ? "bg-blue-50/60" : ""
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-medium">{v.original_filename}</span>
                    <StatusBadge status={v.status} />
                  </span>
                  <span className="text-xs text-neutral-500">
                    {fmtDuration(v.duration_sec)} · {fmtBytes(v.size_bytes)} ·{" "}
                    {new Date(v.created_at).toLocaleDateString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <VideoDetail
              video={selected}
              onClipCreated={() => {
                reload();
              }}
            />
          ) : (
            <EmptyState
              title="Выберите видео"
              hint="Список слева — выберите видео, чтобы увидеть транскрипт, кандидатов и создать клипы."
            />
          )}
        </div>
      )}

      <p className="text-xs text-neutral-500">
        Готовые клипы — в разделе{" "}
        <Link to="/clips" className="text-blue-600 hover:underline">
          Клипы
        </Link>
        .
      </p>
    </div>
  );
}

function toastNoop() {
  /* upload toast is fired inside UploadZone */
}
