// AppShell: sidebar navigation + backend status + system warnings + main area.
import { useState } from "react";
import { NavLink } from "react-router-dom";
import { api, type OverviewStats } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import {
  AlertIcon,
  ChartIcon,
  FilmIcon,
  MenuIcon,
  ScissorsIcon,
  SendIcon,
  XIcon,
} from "../icons";

const NAV = [
  { to: "/", label: "Обзор", icon: <ChartIcon />, end: true },
  { to: "/videos", label: "Видео", icon: <FilmIcon />, end: false },
  { to: "/clips", label: "Клипы", icon: <ScissorsIcon />, end: false },
  { to: "/publish", label: "Публикации", icon: <SendIcon />, end: false },
  { to: "/analytics", label: "Аналитика", icon: <ChartIcon />, end: false },
];

type Health = "ok" | "down" | "checking";

function BackendIndicator({ health }: { health: Health }) {
  const cls =
    health === "ok"
      ? "bg-green-500"
      : health === "down"
        ? "bg-red-500"
        : "bg-neutral-300 motion-safe:animate-pulse motion-reduce:animate-none";
  const text =
    health === "ok" ? "Бэкенд онлайн" : health === "down" ? "Бэкенд недоступен" : "Проверка…";
  return (
    <div className="flex items-center gap-2 px-3 py-2 text-xs text-neutral-500">
      <span className={`h-2 w-2 shrink-0 rounded-full ${cls}`} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

function QueueSummary({ overview }: { overview: OverviewStats | null }) {
  if (!overview) return null;
  const active = (overview.jobs.queued ?? 0) + (overview.jobs.running ?? 0) + (overview.jobs.retrying ?? 0);
  const scheduled = overview.publications.scheduled ?? 0;
  return (
    <div className="flex flex-col gap-1 px-3 pb-2 text-xs text-neutral-500">
      <div className="flex items-center justify-between">
        <span>В очереди</span>
        <span className={active > 0 ? "font-medium text-blue-700" : "text-neutral-500"}>
          {active}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span>По расписанию</span>
        <span className={scheduled > 0 ? "font-medium text-indigo-700" : "text-neutral-500"}>
          {scheduled}
        </span>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [health, setHealth] = useState<Health>("checking");
  const [overview, setOverview] = useState<OverviewStats | null>(null);
  const [navOpen, setNavOpen] = useState(false);

  usePolling(() => {
    api
      .health()
      .then((h) => setHealth(h.status === "ok" ? "ok" : "down"))
      .catch(() => setHealth("down"));
  }, 15000);

  usePolling(() => {
    api
      .overview()
      .then(setOverview)
      .catch(() => {
        /* overview is an enhancement: failures surface in page-level error states */
      });
  }, 20000);

  const failures = overview?.failed_jobs_recent ?? 0;

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium motion-safe:transition-colors ${
      isActive
        ? "bg-neutral-800 text-white"
        : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900"
    } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500`;

  const nav = (
    <nav aria-label="Основная навигация" className="flex flex-col gap-1">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={navLinkClass}
          onClick={() => setNavOpen(false)}
        >
          {item.icon}
          {item.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen bg-neutral-50 text-neutral-900">
      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-neutral-200 bg-white px-3 py-2 lg:hidden">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setNavOpen((v) => !v)}
            aria-expanded={navOpen}
            aria-label={navOpen ? "Закрыть меню" : "Открыть меню"}
            className="rounded-md p-1.5 text-neutral-600 hover:bg-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {navOpen ? <XIcon /> : <MenuIcon />}
          </button>
          <span className="text-sm font-semibold">AI Clipper</span>
        </div>
        <BackendIndicator health={health} />
      </header>
      {navOpen && (
        <div className="border-b border-neutral-200 bg-white px-3 py-2 lg:hidden">{nav}</div>
      )}

      <div className="mx-auto flex w-full max-w-7xl">
        {/* Desktop sidebar */}
        <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col justify-between border-r border-neutral-200 bg-white lg:flex">
          <div className="flex flex-col gap-4 px-3 py-4">
            <div className="px-1">
              <h1 className="text-base font-semibold tracking-tight">AI Clipper</h1>
              <p className="text-xs text-neutral-500">локальный конвейер клипов</p>
            </div>
            {nav}
          </div>
          <div className="border-t border-neutral-200">
            <QueueSummary overview={overview} />
            <BackendIndicator health={health} />
          </div>
        </aside>

        {/* Main */}
        <div className="min-w-0 flex-1">
          {failures > 0 && (
            <div
              role="alert"
              className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800"
            >
              <span className="shrink-0 text-amber-600">
                <AlertIcon />
              </span>
              <span>
                За последние 24 ч упавших задач: {failures}.{" "}
                <NavLink to="/" className="font-medium underline underline-offset-2">
                  Подробности в обзоре
                </NavLink>
              </span>
            </div>
          )}
          <main className="min-w-0 px-4 py-4 lg:px-6 lg:py-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
