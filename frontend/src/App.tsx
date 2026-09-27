import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { UploadPage } from './pages/UploadPage';
import ContractDetailPage from './pages/ContractDetailPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/contracts/demo?offline=1" replace />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/contracts/:id/*" element={<ContractDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
