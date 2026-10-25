import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { OverviewPage } from './pages/OverviewPage';
import { RunOptimizationPage } from './pages/RunOptimizationPage';
import { StationsGridPage } from './pages/StationsGridPage';
import { AllocationResultsPage } from './pages/AllocationResultsPage';
import { FeedbackLoopPage } from './pages/FeedbackLoopPage';
import { HistoryReportsPage } from './pages/HistoryReportsPage';
import { IntegrationHealthPage } from './pages/IntegrationHealthPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="optimize" element={<RunOptimizationPage />} />
          <Route path="stations" element={<StationsGridPage />} />
          <Route path="results" element={<AllocationResultsPage />} />
          <Route path="feedback" element={<FeedbackLoopPage />} />
          <Route path="history" element={<HistoryReportsPage />} />
          <Route path="health" element={<IntegrationHealthPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
};

export default App;
