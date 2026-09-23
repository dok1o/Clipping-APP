// Clips 2.0: list + detail — edit drafts, render w/ progress, video preview, download, platform texts.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  api,
  fmtDuration,
  type Clip,
  type GeneratedTexts,
  type RenderedAsset,
  type TranscriptSegment,
  type Video,
} from "../api";
import { DownloadIcon, PlayIcon, SendIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, Loading } from "../components/ui/Feedback";
import { Field, Select, TextInput } from "../components/ui/Field";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useToast } from "../components/ui/Toast";
import { useJobWait } from "../hooks/useJobWait";

function DraftEditor({
  clip,
  onSaved,
}: {
  clip: Clip;
  onSaved: (c: Clip) => void;
}) {
  const [title, setTitle] = useState(clip.title);
  const [start, setStart] = useState(String(clip.start_sec));
  const [end, setEnd] = useState(String(clip.end_sec));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setTitle(clip.title);
    setStart(String(clip.start_sec));
    setEnd(String(clip.end_sec));
  }, [clip.id, clip.title, clip.start_sec, clip.end_sec]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    const s = Number(start);
    const t = Number(end);
    if (!Number.isFinite(s) || !Number.isFinite(t) || t <= s) {
      setError("Конец должен быть больше начала");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patchClip(clip.id, { title: title.trim(), start_sec: s, end_sec: t });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={save} className="flex flex-col gap-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_5rem_5rem_auto] sm:items-end">
        <Field label="Название" htmlFor="edit-title">
          <TextInput id="edit-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={140} />
        </Field>
        <Field label="Начало, с" htmlFor="edit-start">
          <TextInput id="edit-start" type="number" min={0} step={0.1} value={start} onChange={(e) => setStart(e.target.value)} />
        </Field>
        <Field label="Конец, с" htmlFor="edit-end">
          <TextInput id="edit-end" type="number" min={0} step={0.1} value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <Button type="submit" variant="primary" loading={busy}>
          Сохранить
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

function RenderBlock({ clip, onChanged }: { clip: Clip; onChanged: () => void }) {
  const [asset, setAsset] = useState<RenderedAsset | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const render = useJobWait();
  const toast = useToast();

  const loadAsset = useCallback(() => {
    api
      .getClipAsset(clip.id)
      .then((a) => {
        setAsset(a);
        setError(null);
        return api.getRenderUrl(a.id);
      })
      .then((r) => setUrl(r.url))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setAsset(null);
        else setError(e);
      });
  }, [clip.id]);

  useEffect(loadAsset, [loadAsset]);

  const startRender = async () => {
    try {
      setError(null);
      const job = await api.renderClip(clip.id);
      render.wait(job.id);
    } catch (e) {
      toast.error(e instanceof ApiError ? `${e.code}: ${e.message}` : "Не удалось запустить рендер");
    }
  };

  // when render job finishes -> reload the asset
  useEffect(() => {
    if (render.job?.status === "succeeded") {
      loadAsset();
      onChanged();
    } else if (render.job?.status === "failed") {
      toast.error(`Рендер не удался: ${render.job.error_message ?? "?"}`);
      onChanged();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [render.job?.status]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          onClick={startRender}
          loading={render.running}
          disabled={clip.status === "rendering" || clip.status === "render_queued"}
          icon={<PlayIcon />}
        >
          {asset ? "Перерендерить" : "Рендер 1080×1920"}
        </Button>
        {render.running && (
          <span className="text-xs text-blue-700">
            Рендер… (ffmpeg, задача {render.job?.status})
          </span>
        )}
        {render.job && render.job.status === "failed" && (
          <StatusBadge status="failed" title={render.job.error_message ?? ""} />
        )}
      </div>
      {error ? <ErrorState error={error} onRetry={loadAsset} context="Ассет рендера" /> : null}
      {asset && url && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <video
            controls
            preload="metadata"
            src={url}
            className="h-64 w-auto max-w-full rounded-md border border-neutral-200 bg-black"
          >
            Ваш браузер не поддерживает видео.
          </video>
          <div className="flex flex-col gap-1 text-xs text-neutral-500">
            <span>
              {asset.width}×{asset.height} · {asset.codec_video}/{asset.codec_audio} ·{" "}
              {asset.pix_fmt}
            </span>
            <span>
              {fmtDuration(asset.duration_sec)} · {(asset.size_bytes / 1024 / 1024).toFixed(1)} МБ
            </span>
            <a
              href={url}
              download={`${clip.title.replace(/[\\/:*?"<>|]/g, "_")}.mp4`}
              className="inline-flex items-center gap-1 font-medium text-blue-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            >
              <DownloadIcon /> Скачать MP4
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

function TextsBlock({ clip }: { clip: Clip }) {
  const [platform, setPlatform] = useState("tiktok");
  const [texts, setTexts] = useState<GeneratedTexts | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const toast = useToast();

  const load = useCallback(() => {
    api
      .getClipTexts(clip.id, platform)
      .then((r) => setTexts(r.texts))
      .catch(() => setTexts(null));
  }, [clip.id, platform]);

  useEffect(load, [load]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.generateTexts(clip.id, platform);
      setTexts(r.texts);
      toast.success(`Тексты для ${platform} готовы`);
    } catch (e) {
      setError(e);
      toast.error("Генерация текстов не удалась");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Платформа" htmlFor="texts-platform" className="w-36">
          <Select id="texts-platform" value={platform} onChange={(e) => setPlatform(e.target.value)}>
            <option value="tiktok">tiktok</option>
            <option value="youtube">youtube</option>
          </Select>
        </Field>
        <Button onClick={generate} loading={busy}>
          Сгенерировать тексты
        </Button>
      </div>
      {error ? <ErrorState error={error} onRetry={generate} context="Тексты" /> : null}
      {texts ? (
        <div className="flex flex-col gap-2 rounded-md border border-neutral-200 bg-neutral-50 p-2.5 text-sm">
          <div>
            <p className="text-xs font-medium text-neutral-500">Заголовки</p>
            <ul className="list-inside list-disc">
              {texts.titles.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-xs font-medium text-neutral-500">Описание</p>
            <p className="whitespace-pre-wrap">{texts.description}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-neutral-500">Хэштеги</p>
            <p className="text-blue-700">{texts.hashtags.map((h) => `#${h}`).join(" ")}</p>
          </div>
        </div>
      ) : (
        <p className="text-xs text-neutral-500">
          Текстов для {platform} ещё нет — сгенерируйте (локальный LLM-провайдер).
        </p>
      )}
    </div>
  );
}

function TranscriptContext({ clip }: { clip: Clip }) {
  const [segments, setSegments] = useState<TranscriptSegment[] | null>(null);

  useEffect(() => {
    api
      .getTranscript(clip.video_id)
      .then((page) =>
        setSegments(
          page.items.filter((s) => s.start < clip.end_sec + 1 && s.end > clip.start_sec - 1),
        ),
      )
      .catch(() => setSegments([]));
  }, [clip.video_id, clip.start_sec, clip.end_sec]);

  if (segments === null) return <Loading label="Контекст транскрипта…" />;
  if (segments.length === 0)
    return <p className="text-xs text-neutral-500">Сегментов в диапазоне клипа нет.</p>;
  return (
    <div className="max-h-40 overflow-y-auto rounded-md border border-neutral-200 bg-white">
      <ul className="divide-y divide-neutral-100">
        {segments.map((s) => (
          <li key={s.id} className="flex gap-2 px-2.5 py-1 text-xs">
            <span className="w-16 shrink-0 tabular-nums text-neutral-500">
              {fmtDuration(s.start)}
            </span>
            <span className="min-w-0">{s.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function ClipsPage() {
  const [clips, setClips] = useState<Clip[] | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [videoFilter, setVideoFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(() => {
    api
      .listClips(videoFilter || undefined)
      .then((page) => setClips(page.items))
      .catch(setError);
  }, [videoFilter]);

  useEffect(() => {
    api.listVideos(100).then((p) => setVideos(p.items)).catch(() => undefined);
  }, []);
  useEffect(reload, [reload]);

  if (error) return <ErrorState error={error} onRetry={reload} context="Список клипов" />;
  if (clips === null) return <Loading label="Клипы…" />;

  const selected = clips.find((c) => c.id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Клипы</h1>
          <p className="text-sm text-neutral-500">
            Правка таймкодов, рендер 1080×1920, тексты платформ и публикация.
          </p>
        </div>
        <div className="w-56">
          <Field label="Фильтр по видео" htmlFor="clip-video-filter">
            <Select
              id="clip-video-filter"
              value={videoFilter}
              onChange={(e) => setVideoFilter(e.target.value)}
            >
              <option value="">Все видео</option>
              {videos.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.original_filename}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>

      {clips.length === 0 ? (
        <EmptyState
          title="Клипов нет"
          hint="Создайте клип вручную или из кандидата в разделе «Видео»."
        />
      ) : (
        <div className="grid gap-4 xl:grid-cols-[minmax(300px,420px)_1fr]">
          <ul className="flex max-h-[70vh] flex-col divide-y divide-neutral-100 overflow-y-auto rounded-md border border-neutral-200 bg-white">
            {clips.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => setSelectedId(c.id)}
                  aria-current={c.id === selectedId}
                  className={`flex w-full flex-col gap-0.5 px-3 py-2 text-left text-sm hover:bg-neutral-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 ${
                    c.id === selectedId ? "bg-blue-50/60" : ""
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-medium">{c.title}</span>
                    <StatusBadge status={c.status} />
                  </span>
                  <span className="text-xs text-neutral-500">
                    {fmtDuration(c.start_sec)}–{fmtDuration(c.end_sec)} ·{" "}
                    {(c.end_sec - c.start_sec).toFixed(0)} с
                    {c.score !== null ? ` · score ${c.score.toFixed(2)}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          {selected ? (
            <div className="flex flex-col gap-4 rounded-md border border-neutral-200 bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold">{selected.title}</h2>
                <div className="flex items-center gap-2">
                  <StatusBadge status={selected.status} />
                  <Link to="/publish">
                    <Button size="sm" icon={<SendIcon />}>
                      Опубликовать
                    </Button>
                  </Link>
                </div>
              </div>

              <section className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">
                  {selected.status === "draft" ? "Правка (draft)" : "Таймкоды"}
                </h3>
                {selected.status === "draft" ? (
                  <DraftEditor clip={selected} onSaved={() => reload()} />
                ) : (
                  <p className="text-sm text-neutral-600">
                    {fmtDuration(selected.start_sec)}–{fmtDuration(selected.end_sec)} ·{" "}
                    {(selected.end_sec - selected.start_sec).toFixed(0)} с — редактирование доступно
                    только до рендера.
                  </p>
                )}
              </section>

              <section className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
                <h3 className="text-sm font-medium">Рендер и превью</h3>
                <RenderBlock clip={selected} onChanged={reload} />
              </section>

              <section className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
                <h3 className="text-sm font-medium">Тексты платформ</h3>
                <TextsBlock clip={selected} />
              </section>

              <section className="flex flex-col gap-2 border-t border-neutral-100 pt-3">
                <h3 className="text-sm font-medium">Контекст транскрипта</h3>
                <TranscriptContext clip={selected} />
              </section>
            </div>
          ) : (
            <EmptyState title="Выберите клип" hint="Список слева — выберите клип для работы." />
          )}
        </div>
      )}
    </div>
  );
}
