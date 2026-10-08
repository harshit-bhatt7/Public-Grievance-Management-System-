import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

/**
 * Redirects to /login if unauthenticated, or to / if authenticated but
 * not an officer. This is a UX convenience only — every officer API call
 * is independently re-authorized server-side (department checked from
 * officer_profiles, never trusted from the client), so this route guard
 * being bypassed somehow would not itself expose anything.
 */
function OfficerProtectedRoute({ children }) {
  const { isAuthenticated, initializing, user } = useAuth();

  if (initializing) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user.user_type !== "officer") return <Navigate to="/" replace />;

  return children;
}

export default OfficerProtectedRoute;
