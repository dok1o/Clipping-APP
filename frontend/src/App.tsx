import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ToastProvider } from "./components/ui/Toast";
import AnalyticsPage from "./pages/AnalyticsPage";
import ClipsPage from "./pages/ClipsPage";
import OverviewPage from "./pages/OverviewPage";
import PublishPage from "./pages/PublishPage";
import VideosPage from "./pages/VideosPage";

export default function App() {
  return (
    <ToastProvider>
      <AppShell>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/videos" element={<VideosPage />} />
          <Route path="/videos/:videoId" element={<VideosPage />} />
          <Route path="/clips" element={<ClipsPage />} />
          <Route path="/publish" element={<PublishPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Routes>
      </AppShell>
    </ToastProvider>
  );
}
