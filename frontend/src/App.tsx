import { Link, NavLink, Route, Routes } from "react-router-dom";
import AnalyticsPage from "./pages/AnalyticsPage";
import ClipsPage from "./pages/ClipsPage";
import PublishPage from "./pages/PublishPage";
import VideosPage from "./pages/VideosPage";

export default function App() {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 rounded text-sm font-medium ${
      isActive ? "bg-neutral-800 text-white" : "text-neutral-600 hover:bg-neutral-200"
    }`;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-neutral-200">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-4">
          <Link to="/" className="font-semibold text-neutral-900">
            AI Clipper
          </Link>
          <nav className="flex gap-1">
            <NavLink to="/" end className={linkClass}>
              Videos
            </NavLink>
            <NavLink to="/clips" className={linkClass}>
              Clips
            </NavLink>
            <NavLink to="/publish" className={linkClass}>
              Publish
            </NavLink>
            <NavLink to="/analytics" className={linkClass}>
              Analytics
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<VideosPage />} />
          <Route path="/videos/:videoId" element={<VideosPage />} />
          <Route path="/clips" element={<ClipsPage />} />
          <Route path="/publish" element={<PublishPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Routes>
      </main>
    </div>
  );
}
