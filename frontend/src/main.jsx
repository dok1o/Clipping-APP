import React from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "not configured";

function App() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <section className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-12">
        <div className="space-y-8">
          <div className="space-y-3">
            <p className="text-sm font-medium uppercase tracking-wide text-cyan-300">
              Stage 0 skeleton
            </p>
            <h1 className="text-4xl font-semibold tracking-normal text-white sm:text-5xl">
              AI Clipper & Auto-Publisher
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-zinc-300">
              Frontend is running. This is a minimal React + Tailwind foundation for the future dashboard.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded border border-zinc-800 bg-zinc-900/70 p-5">
              <div className="flex items-center gap-3">
                <span className="h-3 w-3 rounded-full bg-emerald-400" aria-hidden="true" />
                <div>
                  <p className="text-sm text-zinc-400">Frontend status</p>
                  <p className="font-medium text-white">Ready</p>
                </div>
              </div>
            </div>

            <div className="rounded border border-zinc-800 bg-zinc-900/70 p-5">
              <p className="text-sm text-zinc-400">Backend health target</p>
              <p className="mt-1 break-words font-mono text-sm text-zinc-100">{apiBaseUrl}/health</p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
