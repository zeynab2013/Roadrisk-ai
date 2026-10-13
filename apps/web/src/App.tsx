import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { AreasPage } from "@/pages/AreasPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { ModelPage } from "@/pages/ModelPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { PredictPage } from "@/pages/PredictPage";

export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/predict" element={<PredictPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/model" element={<ModelPage />} />
        <Route path="/areas" element={<AreasPage />} />
      </Routes>
    </AppShell>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
