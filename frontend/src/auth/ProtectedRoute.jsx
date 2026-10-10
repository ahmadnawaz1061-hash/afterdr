import { Navigate, useLocation } from 'react-router-dom';
import LoadingState from '../components/common/LoadingState';
import { useAuth } from './AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <LoadingState title="Checking your session…" message="Please wait a moment." />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}
