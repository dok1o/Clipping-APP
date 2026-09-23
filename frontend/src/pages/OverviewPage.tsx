// Overview (home): pipeline state at a glance — counts, queue, failures, metrics, ML.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Job, type OverviewStats } from "../api";
import { usePolling } from "../hooks/usePolling";
import { SparkIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { ErrorState, Loading } from "../components/ui/Feedback";
import { StatusBadge } from "../components/ui/StatusBadge";

function StatCard({
  label,
  value,
  to,
  accent,
}: {
  label: string;
  value: string | number;
  to: string;
  accent?: string;
}) {
  return (
    <Link
      to={to}
      className="flex flex-col gap-1 rounded-md border border-neutral-200 bg-white px-3 py-2.5 hover:border-neutral-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
    >
      <span className="text-xs text-neutral-500">{label}</span>
      <span className={`text-xl font-semibold tabular-nums ${accent ?? "text-neutral-900"}`}>
        {value}
      </span>
    </Link>
  );
}

function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="rounded-md border border-neutral-200 bg-white">
      <div className="flex items-center justify-between border-b border-neutral-100 px-3 py-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      <div className="p-3">{children}</div>
    </section>
  );
}

export default function OverviewPage() {
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [failedJobs, setFailedJobs] = useState<Job[]>([]);

  const reload = useCallback(() => {
    api
      .overview()
      .then((data) => {
        setOverview(data);
        setError(null);
      })
      .catch(setError);
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  usePolling(reload, 15000);

  const loadFailures = useCallback(() => {
    api
      .listJobs({ status: "failed", limit: 10 })
      .then((page) => setFailedJobs(page.items))
      .catch(() => setFailedJobs([]));
  }, []);

  useEffect(() => {
    loadFailures();
  }, [loadFailures]);

  if (error) {
    return <ErrorState error={error} onRetry={reload} context="Загрузка обзора" />;
  }
  if (!overview) return <Loading label="Загрузка состояния конвейера…" />;

  const videosReady = overview.videos.ready ?? 0;
  const videosTotal = Object.values(overview.videos).reduce((a, b) => a + b, 0);
  const clipsRendered = overview.clips.rendered ?? 0;
  const clipsTotal = Object.values(overview.clips).reduce((a, b) => a + b, 0);
  const activeJobs =
    (overview.jobs.queued ?? 0) + (overview.jobs.running ?? 0) + (overview.jobs.retrying ?? 0);
  const published = overview.publications.published ?? 0;
  const scheduled = overview.publications.scheduled ?? 0;
  const failedPubs = overview.publications.failed ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold">Обзор</h1>
          <p className="text-sm text-neutral-500">
            Состояние конвейера: от загрузки до публикаций и обучения.
          </p>
        </div>
        <Link to="/videos">
          <Button variant="primary">Загрузить видео</Button>
        </Link>
      </div>

      {/* Pipeline counters */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Видео (готово)" value={`${videosReady}/${videosTotal}`} to="/videos" />
        <StatCard label="Клипы (отрендерены)" value={`${clipsRendered}/${clipsTotal}`} to="/clips" />
        <StatCard
          label="Задачи активны"
          value={activeJobs}
          to="/"
          accent={activeJobs > 0 ? "text-blue-700" : undefined}
        />
        <StatCard label="Опубликовано" value={published} to="/publish" />
        <StatCard
          label="По расписанию"
          value={scheduled}
          to="/publish"
          accent={scheduled > 0 ? "text-indigo-700" : undefined}
        />
        <StatCard
          label="Сбои за 24 ч"
          value={overview.failed_jobs_recent}
          to="/"
          accent={overview.failed_jobs_recent > 0 ? "text-red-700" : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Metrics summary */}
        <Section title="Последние метрики">
          {overview.latest_metrics.publications === 0 ? (
            <p className="text-sm text-neutral-500">
              Метрик пока нет — синхронизация доступна после публикации (раздел «Аналитика»).
            </p>
          ) : (
            <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-xs text-neutral-500">Публикаций с метриками</dt>
                <dd className="font-semibold tabular-nums">
                  {overview.latest_metrics.publications}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-neutral-500">Просмотры</dt>
                <dd className="font-semibold tabular-nums">{overview.latest_metrics.views}</dd>
              </div>
              <div>
                <dt className="text-xs text-neutral-500">Лайки</dt>
                <dd className="font-semibold tabular-nums">{overview.latest_metrics.likes}</dd>
              </div>
            </dl>
          )}
          {overview.scheduled_next_at && (
            <p className="mt-3 border-t border-neutral-100 pt-2 text-xs text-neutral-500">
              Ближайшая автопубликация:{" "}
              <span className="font-medium text-neutral-700">
                {new Date(overview.scheduled_next_at).toLocaleString()}
              </span>
            </p>
          )}
        </Section>

        {/* ML status */}
        <Section
          title="ML-ранжирование"
          action={
            <Link to="/analytics" className="text-xs font-medium text-blue-600 hover:underline">
              Управлять →
            </Link>
          }
        >
          <div className="flex items-start gap-2 text-sm">
            <span className="mt-0.5 text-neutral-500">
              <SparkIcon />
            </span>
            <div className="flex flex-col gap-1">
              {overview.ml.active_model ? (
                <p>
                  Активна модель{" "}
                  <span className="font-medium">
                    v{overview.ml.active_model.model_version}
                  </span>{" "}
                  ({overview.ml.active_model.backend}) — кандидаты ранжируются ML.
                </p>
              ) : (
                <p className="text-neutral-600">
                  ML-модель не активна — используется эвристика. Модель включается только после
                  прохождения eval-гейта на реальных метриках.
                </p>
              )}
              <p className="text-xs text-neutral-500">
                Строк в обучающем датасете: {overview.ml.dataset_rows}
              </p>
            </div>
          </div>
        </Section>
      </div>

      {/* Failures */}
      <Section
        title={
          overview.failed_jobs_recent > 0
            ? `Требует внимания — упавшие задачи (${overview.failed_jobs_recent} за 24 ч)`
            : "Ошибок нет"
        }
      >
        {failedJobs.length === 0 ? (
          <p className="text-sm text-neutral-500">
            За последние 24 ч упавших задач нет{failedPubs > 0 ? `, но публикаций со статусом failed: ${failedPubs} (см. «Публикации»)` : ""}.
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-neutral-100">
            {failedJobs.map((job) => (
              <li key={job.id} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                <StatusBadge status={job.status} />
                <span className="font-medium">{job.type}</span>
                <span className="text-xs text-neutral-500">{job.ref_type}</span>
                <span className="min-w-0 flex-1 truncate text-xs text-neutral-500" title={job.error_message ?? ""}>
                  {job.error_message ?? "—"}
                </span>
                <span className="text-xs tabular-nums text-neutral-500">
                  {new Date(job.created_at).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}
