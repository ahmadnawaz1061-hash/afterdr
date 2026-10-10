import { BrowserRouter, Route, Routes } from 'react-router-dom';
import DashboardLayout from './components/layout/DashboardLayout';
import LandingPage from './pages/LandingPage';
import DashboardPage from './pages/DashboardPage';
import PrescriptionPage from './pages/PrescriptionPage';
import SchedulerPage from './pages/SchedulerPage';
import AlternativesPage from './pages/AlternativesPage';
import VerificationPage from './pages/VerificationPage';
import ReportingPage from './pages/ReportingPage';
import NotFoundPage from './pages/NotFoundPage';
import AuthPage from './pages/AuthPage';
import { AuthProvider } from './auth/AuthContext';
import ProtectedRoute from './auth/ProtectedRoute';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="login" element={<AuthPage mode="login" />} />
          <Route path="register" element={<AuthPage mode="register" />} />
          <Route element={<DashboardLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="prescription" element={<ProtectedRoute><PrescriptionPage /></ProtectedRoute>} />
          <Route path="scheduler" element={<ProtectedRoute><SchedulerPage /></ProtectedRoute>} />
          <Route path="alternatives" element={<ProtectedRoute><AlternativesPage /></ProtectedRoute>} />
          <Route path="verification" element={<ProtectedRoute><VerificationPage /></ProtectedRoute>} />
          <Route path="reporting" element={<ProtectedRoute><ReportingPage /></ProtectedRoute>} />
          <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
