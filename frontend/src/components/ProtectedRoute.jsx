import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/** Redirects to /login if there is no authenticated session. Shows nothing
 * while the initial silent-refresh check (on app load) is still in flight. */
function ProtectedRoute({ children }) {
  const { isAuthenticated, initializing } = useAuth();

  if (initializing) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return children;
}

export default ProtectedRoute;
