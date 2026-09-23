// StatusBadge: semantic colors for domain statuses (unified mapping, no raw colors in pages).
const MAP: Record<string, string> = {
  // generic
  ok: "bg-green-50 text-green-700 border-green-200",
  ready: "bg-green-50 text-green-700 border-green-200",
  succeeded: "bg-green-50 text-green-700 border-green-200",
  published: "bg-green-50 text-green-700 border-green-200",
  rendered: "bg-green-50 text-green-700 border-green-200",
  active: "bg-green-50 text-green-700 border-green-200",
  // in progress
  queued: "bg-blue-50 text-blue-700 border-blue-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  uploading: "bg-blue-50 text-blue-700 border-blue-200",
  rendering: "bg-blue-50 text-blue-700 border-blue-200",
  render_queued: "bg-blue-50 text-blue-700 border-blue-200",
  processing: "bg-blue-50 text-blue-700 border-blue-200",
  retrying: "bg-blue-50 text-blue-700 border-blue-200",
  scheduled: "bg-indigo-50 text-indigo-700 border-indigo-200",
  draft: "bg-neutral-100 text-neutral-600 border-neutral-200",
  // attention
  failed: "bg-red-50 text-red-700 border-red-200",
  render_failed: "bg-red-50 text-red-700 border-red-200",
  error: "bg-red-50 text-red-700 border-red-200",
  cancelled: "bg-neutral-100 text-neutral-500 border-neutral-200",
  uploading_failed: "bg-red-50 text-red-700 border-red-200",
};

export function StatusBadge({ status, title }: { status: string; title?: string }) {
  const cls = MAP[status] ?? "bg-neutral-100 text-neutral-600 border-neutral-200";
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ${cls}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}
