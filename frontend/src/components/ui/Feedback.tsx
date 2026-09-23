// Feedback primitives: EmptyState, ErrorState (technical detail on expand), Progress.
import { AlertIcon } from "../icons";

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-neutral-300 bg-neutral-50 px-4 py-8 text-center">
      <p className="text-sm font-medium text-neutral-700">{title}</p>
      {hint && <p className="max-w-md text-xs text-neutral-500">{hint}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  context,
}: {
  error: unknown;
  onRetry?: () => void;
  context?: string;
}) {
  const message = error instanceof Error ? error.message : String(error);
  const code = (error as { code?: string } | null)?.code;
  const status = (error as { status?: number } | null)?.status;
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2.5">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 text-red-600">
          <AlertIcon />
        </span>
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-medium text-red-800">
            {context ? `Ошибка: ${context}` : "Что-то пошло не так"}
          </p>
          <p className="break-words text-red-700">{message}</p>
          {(code || status) && (
            <details className="mt-1 text-xs text-red-600">
              <summary className="cursor-pointer select-none">Технические детали</summary>
              <span className="ml-3">
                {status ? `HTTP ${status}` : ""}
                {status && code ? " · " : ""}
                {code ? `code: ${code}` : ""}
              </span>
            </details>
          )}
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 rounded-md border border-red-300 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
            >
              Повторить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Progress({ value, label }: { value: number; label?: string }) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? "Прогресс"}
      className="h-1.5 w-full overflow-hidden rounded bg-neutral-200"
    >
      <div
        className="h-full rounded bg-blue-600 motion-safe:transition-[width] motion-reduce:transition-none"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export function Loading({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-1 py-4 text-sm text-neutral-500" role="status">
      <span
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-neutral-400 border-t-transparent motion-reduce:animate-none"
        aria-hidden="true"
      />
      {label}
    </div>
  );
}
