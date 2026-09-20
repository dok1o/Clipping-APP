import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type Metric, type Publication, type TrainingRun } from "../api";

interface Row {
  publication: Publication;
  metrics: Metric[];
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span className="text-neutral-400 text-xs">мало точек</span>;
  const max = Math.max(...values, 1);
  const points = values
    .map((v, i) => `${(i / (values.length - 1)) * 100},${30 - (v / max) * 28}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 30" className="w-24 h-8" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="rgb(29 78 216)" strokeWidth="1.5" />
    </svg>
  );
}

export default function AnalyticsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState<TrainingRun[]>([]);
  const [datasetRows, setDatasetRows] = useState<number | null>(null);
  const [trainMsg, setTrainMsg] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const pubs = await api.listPublications();
    const published = pubs.items.filter((p) => p.status === "published");
    const withMetrics = await Promise.all(
      published.map(async (publication) => {
        const metrics = await api.getMetrics(publication.id).catch(() => ({ items: [] as Metric[], total: 0 }));
        return { publication, metrics: metrics.items };
      }),
    );
    setRows(withMetrics);
  }, []);

  useEffect(() => {
    reload().catch((e) => setError(String(e)));
    api.listTrainingRuns().then((r) => setRuns(r.items)).catch(() => {});
    api.datasetStatus().then((s) => setDatasetRows(s.rows)).catch(() => {});
  }, [reload]);

  const train = async () => {
    setTrainMsg("Обучение…");
    try {
      await api.trainModel();
      await new Promise((r) => setTimeout(r, 2500)); // eager jobs run inline
      const r = await api.listTrainingRuns();
      setRuns(r.items);
      const latest = r.items[0];
      setTrainMsg(
        latest
          ? latest.gate_passed
            ? `Модель обучена (spearman ${latest.val_spearman} > baseline ${latest.baseline_spearman}) — ML-rerank активен`
            : `Гейт не пройден (${latest.status}) — остаётся эвристика: ${latest.error_message ?? ""}`
          : null
      );
    } catch (e) {
      setTrainMsg(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    }
  };

  const syncAll = async () => {
    setBusy(true);
    setError(null);
    try {
      for (const row of rows) {
        await api.syncMetrics(row.publication.id).catch((e) => {
          if (e instanceof ApiError && e.code === "publication_not_published") return;
          throw e;
        });
      }
      await new Promise((r) => setTimeout(r, 1500)); // jobs are eager in dev
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Analytics</h1>
        <button
          onClick={syncAll}
          disabled={busy || rows.length === 0}
          className="px-3 py-1.5 border rounded text-sm hover:bg-neutral-50 disabled:opacity-50"
        >
          Синхронизировать метрики
        </button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}

      <section className="border border-neutral-200 rounded p-3 bg-white">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-medium">
            ML-ранжирование {datasetRows !== null && <span className="text-neutral-400">(строк данных: {datasetRows})</span>}
          </h2>
          <button onClick={train} className="px-3 py-1.5 border rounded text-sm hover:bg-neutral-50">
            Обучить модель
          </button>
        </div>
        {trainMsg && <p className="text-xs text-neutral-600 mb-2">{trainMsg}</p>}
        {runs.length > 0 && (
          <table className="w-full text-xs">
            <thead className="text-left text-neutral-500">
              <tr>
                <th className="p-1">Дата</th>
                <th className="p-1">Строк</th>
                <th className="p-1">Spearman ML</th>
                <th className="p-1">Baseline</th>
                <th className="p-1">Гейт</th>
                <th className="p-1">Статус</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-neutral-100">
                  <td className="p-1">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="p-1">{r.n_rows}</td>
                  <td className="p-1">{r.val_spearman ?? "—"}</td>
                  <td className="p-1">{r.baseline_spearman ?? "—"}</td>
                  <td className={"p-1 " + (r.gate_passed ? "text-green-600" : "text-red-600")}>
                    {r.gate_passed ? "пройден" : "не пройден"}
                  </td>
                  <td className="p-1">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {runs.length === 0 && (
          <p className="text-xs text-neutral-500">
            Обучающих прогонов ещё нет. Модель обучается на связках «фичи клипа → метрики публикации»
            и активируется, только если обгоняет эвристику на валидации.
          </p>
        )}
      </section>

      <table className="w-full text-sm bg-white border border-neutral-200 rounded">
        <thead className="bg-neutral-50 text-left text-neutral-500">
          <tr>
            <th className="p-2">Публикация</th>
            <th className="p-2">Платформа</th>
            <th className="p-2">Просмотры</th>
            <th className="p-2">Лайки</th>
            <th className="p-2">Комменты</th>
            <th className="p-2">Репосты</th>
            <th className="p-2">Динамика views</th>
            <th className="p-2">Синхронизаций</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ publication, metrics }) => {
            const latest = metrics[metrics.length - 1];
            return (
              <tr key={publication.id} className="border-t border-neutral-100">
                <td className="p-2">
                  {publication.external_post_id?.slice(0, 12) ?? publication.id.slice(0, 8)}
                </td>
                <td className="p-2">{publication.platform}</td>
                <td className="p-2">{latest?.views ?? "—"}</td>
                <td className="p-2">{latest?.likes ?? "—"}</td>
                <td className="p-2">{latest?.comments ?? "—"}</td>
                <td className="p-2">{latest?.shares ?? "—"}</td>
                <td className="p-2">
                  <Sparkline values={metrics.map((m) => m.views ?? 0)} />
                </td>
                <td className="p-2">{metrics.length}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td className="p-3 text-neutral-500" colSpan={8}>
                Нет опубликованных публикаций — метрики появятся после публикации.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
