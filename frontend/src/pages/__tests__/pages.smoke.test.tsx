// Page smoke tests: render shells with a mocked API client (no network).
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/Toast";

const notFound = (code: string) =>
  Object.assign(new Error("нет данных"), { status: 409, code });

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    api: {
      health: vi.fn().mockResolvedValue({ status: "ok", version: "0.1.0", checks: {} }),
      overview: vi.fn().mockResolvedValue({
        videos: { ready: 1 },
        clips: { rendered: 2 },
        jobs: { queued: 1 },
        publications: { published: 3, scheduled: 1 },
        scheduled_next_at: null,
        failed_jobs_recent: 0,
        latest_metrics: { publications: 0, views: 0, likes: 0, comments: 0, shares: 0 },
        ml: { dataset_rows: 4, active_model: null },
      }),
      listJobs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      listVideos: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      listClips: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      listPublications: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      listPlatformAccounts: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      listTrainingRuns: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      datasetStatus: vi.fn().mockResolvedValue({ rows: 0, skipped: {}, targets: [] }),
      activeModel: vi.fn().mockResolvedValue({ active: false, model_version: null }),
      getTranscript: vi.fn().mockRejectedValue(notFound("transcript_missing")),
      listCandidates: vi.fn().mockRejectedValue(notFound("transcript_missing")),
    },
  };
});

function withRouter(el: React.ReactElement) {
  return (
    <MemoryRouter>
      <ToastProvider>{el}</ToastProvider>
    </MemoryRouter>
  );
}

describe("AppShell + pages smoke", () => {
  it("renders navigation with all sections and backend indicator", async () => {
    const { default: App } = await import("../../App");
    render(withRouter(<App />));
    expect(screen.getAllByRole("heading", { name: "AI Clipper" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Обзор/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Видео/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Клипы/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Публикации/ })).toBeTruthy();
    await waitFor(() =>
      expect(screen.getAllByText("Бэкенд онлайн").length).toBeGreaterThan(0),
    );
  });

  it("OverviewPage shows pipeline counters from the API", async () => {
    const { default: OverviewPage } = await import("../OverviewPage");
    render(withRouter(<OverviewPage />));
    await waitFor(() => expect(screen.getByText("1/1")).toBeTruthy()); // videos ready/total
    expect(screen.getByText("2/2")).toBeTruthy(); // clips rendered
    expect(screen.getByText("Строк в обучающем датасете: 4")).toBeTruthy();
    expect(screen.getByText("Ошибок нет")).toBeTruthy();
  });

  it("VideosPage shows upload zone and empty state", async () => {
    const { default: VideosPage } = await import("../VideosPage");
    render(withRouter(<VideosPage />));
    await waitFor(() => expect(screen.getByText("Видео пока не загружены")).toBeTruthy());
    expect(
      screen.getByRole("button", { name: /Загрузить видео/ }),
    ).toBeTruthy();
  });

  it("ClipsPage shows empty state", async () => {
    const { default: ClipsPage } = await import("../ClipsPage");
    render(withRouter(<ClipsPage />));
    await waitFor(() => expect(screen.getByText("Клипов нет")).toBeTruthy());
  });

  it("PublishPage shows accounts section and platform limits", async () => {
    const { default: PublishPage } = await import("../PublishPage");
    render(withRouter(<PublishPage />));
    await waitFor(() => expect(screen.getByText("Аккаунты платформ")).toBeTruthy());
    expect(screen.getByText("История публикаций")).toBeTruthy();
    expect(screen.getByText(/unaudited/)).toBeTruthy();
  });

  it("AnalyticsPage shows empty metrics and ML section", async () => {
    const { default: AnalyticsPage } = await import("../AnalyticsPage");
    render(withRouter(<AnalyticsPage />));
    await waitFor(() => expect(screen.getByText("ML-ранжирование")).toBeTruthy());
    expect(screen.getByText("Обучений ещё не было")).toBeTruthy();
  });
});
