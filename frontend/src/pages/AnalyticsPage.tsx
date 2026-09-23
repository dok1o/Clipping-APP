// Analytics 2.0: platform comparison, best clips, dynamics, dataset reasons, ML runs + active model.
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type Clip,
  type Metric,
  type Publication,
  type TrainingRun,
} from "../api";
import { RefreshIcon, SparkIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { EmptyState, ErrorState, Loading } from "../components/ui/Feedback";
import { StatusBadge } from "../components/ui/StatusBadge";
import { useToast } from "../components/ui/Toast";
import { useJobWait } from "../hooks/useJobWait";

interface Row {
  publication: Publication;
  metrics: Metric[];
  clip?: Clip;
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2)
    return <span className="text-xs text-neutral-500">мало точек</span>;
  const max = Math.max(...values, 1);
  const points = values
    .map((v, i) => `${(i / (values.length - 1)) * 100},${30 - (v / max) * 28}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-24" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" stroke="rgb(37 99 235)" strokeWidth="1.5" />
    </svg>
  );
}

function PlatformBars({ rows }: { rows: Row[] }) {
  const byPlatform = new Map<string, { views: number; likes: number; comments: number }>();
  for (const row of rows) {
    const latest = row.metrics[row.metrics.length - 1];
    if (!latest) continue;
    const agg = byPlatform.get(row.publication.platform) ?? { views: 0, likes: 0, comments: 0 };
    agg.views += latest.views ?? 0;
    agg.likes += latest.likes ?? 0;
    agg.comments += latest.comments ?? 0;
    byPlatform.set(row.publication.platform, agg);
  }
  if (byPlatform.size === 0) return <p className="text-sm text-neutral-500">Нет метрик.</p>;
  const maxViews = Math.max(...[...byPlatform.values()].map((v) => v.views), 1);
  return (
    <div className="flex flex-col gap-2">
      {[...byPlatform.entries()].map(([platform, agg]) => (
        <div key={platform} className="flex items-center gap-3 text-sm">
          <span className="w-16 shrink-0 font-medium">{platform}</span>
          <div className="h-4 min-w-0 flex-1 overflow-hidden rounded bg-neutral-100">
            <div
              className="h-full rounded bg-blue-600"
              style={{ width: `${Math.max(2, (agg.views / maxViews) * 100)}%` }}
            />
          </div>
          <span className="w-40 shrink-0 text-right text-xs tabular-nums text-neutral-500">
            {agg.views} просм. · {agg.likes} лайк. · {agg.comments} комм.
          </span>
        </div>
      ))}
    </div>
  );
}

function BestClips({ rows }: { rows: Row[] }) {
  const best = rows
    .map((row) => ({ row, latest: row.metrics[row.metrics.length - 1] }))
    .filter((r) => r.latest && (r.latest.views ?? 0) > 0)
    .sort((a, b) => (b.latest!.views ?? 0) - (a.latest!.views ?? 0))
    .slice(0, 5);
  if (best.length === 0)
    return <p className="text-sm text-neutral-500">Пока нет просмотров для сравнения.</p>;
  return (
    <ol className="flex flex-col divide-y divide-neutral-100">
      {best.map(({ row, latest }, i) => (
        <li key={row.publication.id} className="flex items-center gap-2 py-1.5 text-sm">
          <span className="w-5 text-center text-xs font-semibold text-neutral-500">{i + 1}</span>
          <span className="min-w-0 flex-1 truncate">{row.clip?.title ?? row.publication.clip_id.slice(0, 8)}</span>
          <span className="text-xs text-neutral-500">{row.publication.platform}</span>
          <span className="w-16 text-right font-medium tabular-nums">{latest!.views ?? 0}</span>
          <span className="w-24 text-right text-xs tabular-nums text-neutral-500">
            ER {latest!.views ? (((latest!.likes ?? 0) + (latest!.comments ?? 0)) / latest!.views * 100).toFixed(1) : "—"}%
          </span>
        </li>
      ))}
    </ol>
  );
}

function MlSection() {
  const [runs, setRuns] = useState<TrainingRun[] | null>(null);
  const [dataset, setDataset] = useState<{ rows: number; skipped: Record<string, number>; targets: string[] } | null>(null);
  const [active, setActive] = useState<{ active: boolean; model_version: string | null } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const train = useJobWait();
  const toast = useToast();

  const reload = useCallback(() => {
    api.listTrainingRuns().then((r) => setRuns(r.items)).catch(setError);
    api.datasetStatus().then(setDataset).catch(() => undefined);
    api.activeModel().then(setActive).catch(() => undefined);
  }, []);

  useEffect(reload, [reload]);
  useEffect(() => {
    if (train.job?.status === "succeeded") {
      reload();
      toast.success("Обучение завершено — см. решение гейта ниже");
    } else if (train.job?.status === "failed") {
      toast.error(`Обучение не удалось: ${train.job.error_message ?? "?"}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [train.job?.status]);

  const startTrain = async () => {
    try {
      const r = await api.trainModel();
      train.wait(r.job_id);
      toast.info("Обучение запущено (Job ml_train)");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Не удалось запустить обучение");
    }
  };

  return (
    <section className="rounded-md border border-neutral-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-100 px-3 py-2">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold">
          <SparkIcon /> ML-ранжирование
        </h2>
        <div className="flex items-center gap-2">
          {active && (
            <StatusBadge
              status={active.active ? "active" : "draft"}
              title={active.active ? `v${active.model_version}` : "эвристика"}
            />
          )}
          <Button size="sm" variant="primary" onClick={startTrain} loading={train.running}>
            Обучить модель
          </Button>
        </div>
      </div>
      <div className="flex flex-col gap-3 p-3">
        {error ? <ErrorState error={error} onRetry={reload} context="ML" /> : null}
        {train.running && (
          <p className="text-xs text-blue-700">Обучение идёт (Job {train.job?.status})…</p>
        )}
        {dataset && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
            <span>
              Строк датасета: <b className="text-neutral-700">{dataset.rows}</b>
            </span>
            {Object.entries(dataset.skipped).map(([reason, count]) => (
              <span key={reason}>
                пропущено ({reason}): <b className="text-neutral-700">{count}</b>
              </span>
            ))}
            {dataset.targets.length > 0 && <span>цели: {dataset.targets.join(", ")}</span>}
          </div>
        )}
        {active && (
          <p className="text-xs text-neutral-500">
            {active.active
              ? `Активна модель v${active.model_version} — кандидаты ранжируются ML.`
              : "Активной модели нет — работает эвристика. Модель включится только после прохождения eval-гейта."}
          </p>
        )}
        {runs === null ? (
          <Loading label="Прогоны обучения…" />
        ) : runs.length === 0 ? (
          <EmptyState
            title="Обучений ещё не было"
            hint="Модель обучается на связках «фичи клипа → метрики публикации» и включается, только если обгоняет эвристику."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500">
                  <th className="py-1.5 pr-3 font-medium">Дата</th>
                  <th className="py-1.5 pr-3 font-medium">Строк</th>
                  <th className="py-1.5 pr-3 font-medium">Spearman ML</th>
                  <th className="py-1.5 pr-3 font-medium">Baseline</th>
                  <th className="py-1.5 pr-3 font-medium">Гейт</th>
                  <th className="py-1.5 pr-3 font-medium">Статус</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-neutral-100">
                    <td className="py-1.5 pr-3 text-xs tabular-nums">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">{r.n_rows}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{r.val_spearman ?? "—"}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{r.baseline_spearman ?? "—"}</td>
                    <td className="py-1.5 pr-3">
                      <span className={r.gate_passed ? "text-green-700" : "text-red-700"}>
                        {r.gate_passed ? "пройден" : "не пройден"}
                      </span>
                    </td>
                    <td className="py-1.5 pr-3">
                      <StatusBadge status={r.status} title={r.error_message ?? ""} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

export default function AnalyticsPage() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const reload = useCallback(() => {
    Promise.all([api.listPublications(), api.listClips()])
      .then(async ([pubs, clips]) => {
        const published = pubs.items.filter((p) => p.status === "published");
        const loaded = await Promise.all(
          published.map(async (publication) => {
            const metrics = await api
              .getMetrics(publication.id)
              .catch(() => ({ items: [] as Metric[], total: 0 }));
            return {
              publication,
              metrics: metrics.items,
              clip: clips.items.find((c) => c.id === publication.clip_id),
            };
          }),
        );
        setRows(loaded);
        setError(null);
      })
      .catch(setError);
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const syncAll = async () => {
    if (!rows) return;
    setBusy(true);
    try {
      for (const row of rows) {
        await api.syncMetrics(row.publication.id).catch(() => undefined);
      }
      await new Promise((r) => setTimeout(r, 1500)); // eager jobs run inline in dev
      await reload();
      toast.success("Метрики синхронизированы");
    } finally {
      setBusy(false);
    }
  };

  if (error) return <ErrorState error={error} onRetry={reload} context="Аналитика" />;
  if (rows === null) return <Loading label="Аналитика…" />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Аналитика</h1>
          <p className="text-sm text-neutral-500">
            Метрики из официальных API, сравнение платформ и обучение ранжированию.
          </p>
        </div>
        <Button onClick={syncAll} loading={busy} icon={<RefreshIcon />} disabled={rows.length === 0}>
          Синхронизировать метрики
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-md border border-neutral-200 bg-white p-3">
          <h2 className="mb-2 text-sm font-semibold">Платформы (последние метрики)</h2>
          <PlatformBars rows={rows} />
        </section>
        <section className="rounded-md border border-neutral-200 bg-white p-3">
          <h2 className="mb-2 text-sm font-semibold">Лучшие клипы</h2>
          <BestClips rows={rows} />
        </section>
      </div>

      <section className="rounded-md border border-neutral-200 bg-white">
        <div className="border-b border-neutral-100 px-3 py-2">
          <h2 className="text-sm font-semibold">Публикации и динамика</h2>
        </div>
        <div className="overflow-x-auto p-3">
          {rows.length === 0 ? (
            <EmptyState
              title="Опубликованных публикаций нет"
              hint="Метрики появятся после публикации (раздел «Публикации»)."
            />
          ) : (
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500">
                  <th className="py-1.5 pr-3 font-medium">Публикация</th>
                  <th className="py-1.5 pr-3 font-medium">Платформа</th>
                  <th className="py-1.5 pr-3 font-medium">Просмотры</th>
                  <th className="py-1.5 pr-3 font-medium">Лайки</th>
                  <th className="py-1.5 pr-3 font-medium">Комменты</th>
                  <th className="py-1.5 pr-3 font-medium">Репосты</th>
                  <th className="py-1.5 pr-3 font-medium">Динамика</th>
                  <th className="py-1.5 pr-3 font-medium">Синк.</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ publication, metrics, clip }) => {
                  const latest = metrics[metrics.length - 1];
                  return (
                    <tr key={publication.id} className="border-b border-neutral-100">
                      <td className="max-w-[12rem] truncate py-1.5 pr-3" title={clip?.title}>
                        {clip?.title ?? publication.external_post_id?.slice(0, 10) ?? "—"}
                      </td>
                      <td className="py-1.5 pr-3">{publication.platform}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{latest?.views ?? "—"}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{latest?.likes ?? "—"}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{latest?.comments ?? "—"}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{latest?.shares ?? "—"}</td>
                      <td className="py-1.5 pr-3">
                        <Sparkline values={metrics.map((m) => m.views ?? 0)} />
                      </td>
                      <td className="py-1.5 pr-3 tabular-nums text-neutral-500">{metrics.length}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <MlSection />
    </div>
  );
}
