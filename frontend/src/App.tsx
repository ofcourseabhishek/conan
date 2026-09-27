import { BrowserRouter, Navigate, Route, Routes, useSearchParams } from 'react-router-dom';
import LandingPage from './pages/LandingPage';
import { UploadPage } from './pages/UploadPage';
import ContractDetailPage from './pages/ContractDetailPage';

// "/?offline=1" is the TRD's offline-mode URL; it opens the bundled read-only fixture.
function Home() {
  const [searchParams] = useSearchParams();
  if (searchParams.get('offline') === '1') {
    return <Navigate to="/contracts/demo?offline=1" replace />;
  }
  return <LandingPage />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/contracts/:id/*" element={<ContractDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
