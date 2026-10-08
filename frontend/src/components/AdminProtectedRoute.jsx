import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
export default function AdminProtectedRoute({ children }) {
  const { user, isAuthenticated, initializing } = useAuth();
  if (initializing) return <p>Loading…</p>;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.user_type !== "admin") return <Navigate to="/" replace />;
  return children;
}
