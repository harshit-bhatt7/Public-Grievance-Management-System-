import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import {
  Landmark,
  FileText,
  Search,
  BarChart3,
  Building2,
  ShieldCheck,
  Sparkles,
  Menu,
  X,
  Settings,
  LogOut,
  LayoutDashboard,
  ClipboardList,
  BrainCircuit,
  FolderKanban,
  ArrowRight,
  Lock,
  Activity,
  ClipboardCheck,
} from "lucide-react";
import "./App.css";
import { getApiStatus, getHealth, getDatabaseHealth } from "./services/api";
import { useAuth } from "./context/AuthContext.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import RegisterPage from "./pages/RegisterPage.jsx";
import NewGrievancePage from "./pages/NewGrievancePage.jsx";
import MyGrievancesPage from "./pages/MyGrievancesPage.jsx";
import GrievanceDetailPage from "./pages/GrievanceDetailPage.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import OfficerProtectedRoute from "./components/OfficerProtectedRoute.jsx";
import OfficerDashboardPage from "./pages/OfficerDashboardPage.jsx";
import OfficerGrievanceListPage from "./pages/OfficerGrievanceListPage.jsx";
import OfficerGrievanceDetailPage from "./pages/OfficerGrievanceDetailPage.jsx";
import CitizenAIAssistantPage from "./pages/CitizenAIAssistantPage.jsx";
import OfficerAIPage from "./pages/OfficerAIPage.jsx";
import AdminAIPage from "./pages/AdminAIPage.jsx";
import ResolutionReviewPage from "./pages/ResolutionReviewPage.jsx";
import AdminDashboardPage from "./pages/AdminDashboardPage.jsx";
import AdminManagementPage from "./pages/AdminManagementPage.jsx";
import AdminProtectedRoute from "./components/AdminProtectedRoute.jsx";
import NotificationBell from "./components/NotificationBell.jsx";
import NotificationCenterPage from "./pages/NotificationCenterPage.jsx";
import NotificationPreferencesPage from "./pages/NotificationPreferencesPage.jsx";
import PublicStatisticsPage from "./pages/PublicStatisticsPage.jsx";
import PublicProjectsPage from "./pages/PublicProjectsPage.jsx";
import ProjectDetailPage from "./pages/ProjectDetailPage.jsx";
import AdminProjectsPage from "./pages/AdminProjectsPage.jsx";
import AdminProjectCreatePage from "./pages/AdminProjectCreatePage.jsx";
import AdminProjectDetailPage from "./pages/AdminProjectDetailPage.jsx";

function StatusBadge({ state }) {
  // state: "pending" | "ok" | "error"
  const label = state === "pending" ? "checking..." : state === "ok" ? "connected" : "unavailable";
  return <span className={`badge ${state === "pending" ? "pending" : state === "ok" ? "ok" : "error"}`}>{label}</span>;
}

const QUICK_ACTIONS = [
  {
    icon: FileText,
    title: "Submit a Grievance",
    description: "Report a civic issue in your area — potholes, sanitation, water supply and more.",
    to: "/complaints/new",
    cta: "File a complaint",
  },
  {
    icon: Search,
    title: "Track a Grievance",
    description: "Follow the status and resolution timeline of complaints you've already filed.",
    to: "/complaints",
    cta: "View my complaints",
  },
  {
    icon: Building2,
    title: "Explore Government Projects",
    description: "See ongoing and completed public works, budgets and timelines in your area.",
    to: "/projects",
    cta: "Browse projects",
  },
  {
    icon: BarChart3,
    title: "View Public Statistics",
    description: "Transparent, privacy-preserving resolution rates and civic performance rankings.",
    to: "/statistics",
    cta: "Open statistics",
  },
];

const TRUST_POINTS = [
  { icon: ShieldCheck, label: "Privacy-protected identities" },
  { icon: Lock, label: "Tamper-evident audit trail" },
  { icon: Activity, label: "Transparent resolution tracking" },
  { icon: Sparkles, label: "AI-assisted, human-reviewed" },
];

function HomePage() {
  const [apiStatus, setApiStatus] = useState("pending");
  const [health, setHealth] = useState("pending");
  const [dbHealth, setDbHealth] = useState("pending");
  const { user, isAuthenticated } = useAuth();

  useEffect(() => {
    getApiStatus()
      .then(() => setApiStatus("ok"))
      .catch(() => setApiStatus("error"));

    getHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("error"));

    getDatabaseHealth()
      .then((data) => setDbHealth(data.database === "connected" ? "ok" : "error"))
      .catch(() => setDbHealth("error"));
  }, []);

  return (
    <div className="app-shell home-shell">
      <section className="hero">
        <span className="hero-eyebrow">
          <Landmark size={14} /> Public Grievance Management &amp; Civic Accountability
        </span>
        <h1>A transparent way for citizens and government to solve civic problems together</h1>
        <p>
          Submit and track grievances, follow real government project progress, and see privacy-preserving
          public statistics that hold departments accountable — all in one civic platform.
        </p>
        <div className="hero-actions">
          {isAuthenticated ? (
            <>
              <Link className="btn-primary" to="/complaints/new">
                <FileText size={16} /> File a New Complaint
              </Link>
              <Link className="btn-outline" to="/complaints">
                <Search size={16} /> View My Complaints
              </Link>
            </>
          ) : (
            <>
              <Link className="btn-primary" to="/register">
                <FileText size={16} /> Get Started
              </Link>
              <Link className="btn-outline" to="/login">
                Log In <ArrowRight size={16} />
              </Link>
            </>
          )}
        </div>
      </section>

      {isAuthenticated && (
        <div className="status-card" style={{ maxWidth: "100%" }}>
          <div className="status-row">
            <span className="status-label">Signed in as</span>
            <span>
              <strong>{user.name}</strong>
            </span>
          </div>
          <div className="status-row">
            <span className="status-label">Account type</span>
            <span className="badge neutral">{user.user_type}</span>
          </div>
          {user.user_type === "officer" && (
            <div className="status-row">
              <span className="status-label">Officer tools</span>
              <Link to="/officer/dashboard" className="btn-link">
                Go to Officer Dashboard <ArrowRight size={14} />
              </Link>
            </div>
          )}
          {user.user_type === "admin" && (
            <div className="status-row">
              <span className="status-label">Admin tools</span>
              <Link to="/admin/dashboard" className="btn-link">
                Go to Admin Dashboard <ArrowRight size={14} />
              </Link>
            </div>
          )}
        </div>
      )}

      <div className="section-title">
        <h2>What would you like to do?</h2>
      </div>
      <div className="action-grid">
        {QUICK_ACTIONS.map(({ icon: Icon, title, description, to, cta }) => (
          <Link className="action-card" to={to} key={title}>
            <span className="action-card-icon">
              <Icon size={20} />
            </span>
            <h3>{title}</h3>
            <p>{description}</p>
            <span className="btn-link" style={{ marginTop: "auto" }}>
              {cta} <ArrowRight size={14} />
            </span>
          </Link>
        ))}
      </div>

      <div className="trust-strip">
        {TRUST_POINTS.map(({ icon: Icon, label }) => (
          <div key={label}>
            <Icon size={18} />
            {label}
          </div>
        ))}
      </div>

      <div className="section-title">
        <h2>System Status</h2>
      </div>
      <div className="status-card" style={{ maxWidth: "420px" }}>
        <div className="status-row">
          <span className="status-label">Backend API</span>
          <StatusBadge state={apiStatus} />
        </div>
        <div className="status-row">
          <span className="status-label">Health Check</span>
          <StatusBadge state={health} />
        </div>
        <div className="status-row">
          <span className="status-label">Database</span>
          <StatusBadge state={dbHealth} />
        </div>
      </div>

      <p className="footer-note">
        Public Grievance Management System — civic grievance workflow, government project transparency,
        resolution governance and notifications.
      </p>
    </div>
  );
}

function NavBar() {
  const { isAuthenticated, user, logout, initializing } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand" onClick={closeMenu}>
        <span className="navbar-brand-mark">
          <Landmark size={18} />
        </span>
        <span className="navbar-brand-text">
          PGMS
          <small>Civic Grievance Platform</small>
        </span>
      </Link>

      <button
        type="button"
        className="navbar-toggle"
        aria-label={menuOpen ? "Close menu" : "Open menu"}
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((v) => !v)}
      >
        {menuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <div className={`navbar-links${menuOpen ? " open" : ""}`} onClick={closeMenu}>
        <Link to="/statistics">
          <BarChart3 size={15} /> Statistics
        </Link>
        <Link to="/projects">
          <Building2 size={15} /> Projects
        </Link>
        {initializing ? null : isAuthenticated ? (
          <>
            {user.user_type === "officer" ? (
              <>
                <Link to="/officer/dashboard">
                  <LayoutDashboard size={15} /> Dashboard
                </Link>
                <Link to="/officer/grievances">
                  <ClipboardList size={15} /> Grievances
                </Link>
                <Link to="/officer/ai">
                  <BrainCircuit size={15} /> AI Tools
                </Link>
              </>
            ) : user.user_type === "citizen" ? (
              <>
                <Link to="/complaints/new">
                  <FileText size={15} /> New Complaint
                </Link>
                <Link to="/complaints">
                  <ClipboardCheck size={15} /> My Complaints
                </Link>
                <Link to="/ai-assistant">
                  <BrainCircuit size={15} /> AI Assistant
                </Link>
              </>
            ) : null}
            {user.user_type === "admin" && (
              <>
                <Link to="/admin/dashboard">
                  <LayoutDashboard size={15} /> Admin Dashboard
                </Link>
                <Link to="/admin/projects">
                  <FolderKanban size={15} /> Projects
                </Link>
                <Link to="/admin/ai">
                  <BrainCircuit size={15} /> AI Governance
                </Link>
              </>
            )}
            <span className="navbar-divider" />
            <NotificationBell />
            <Link to="/notifications/preferences">
              <Settings size={15} /> Settings
            </Link>
            <span className="navbar-user">{user.name}</span>
            <button type="button" className="btn-link" onClick={() => logout()}>
              <LogOut size={15} /> Log out
            </button>
          </>
        ) : (
          <>
            <Link to="/login">Log In</Link>
            <Link to="/register" className="btn-primary" style={{ padding: "0.5rem 0.9rem" }}>
              Register
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}

function App() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/statistics" element={<PublicStatisticsPage />} />
        <Route path="/projects" element={<PublicProjectsPage />} />
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/complaints/new"
          element={
            <ProtectedRoute>
              <NewGrievancePage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/complaints"
          element={
            <ProtectedRoute>
              <MyGrievancesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/complaints/:grievanceNumber/resolution"
          element={
            <ProtectedRoute>
              <ResolutionReviewPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/complaints/:grievanceNumber"
          element={
            <ProtectedRoute>
              <GrievanceDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/officer/dashboard"
          element={
            <OfficerProtectedRoute>
              <OfficerDashboardPage />
            </OfficerProtectedRoute>
          }
        />
        <Route
          path="/officer/grievances"
          element={
            <OfficerProtectedRoute>
              <OfficerGrievanceListPage />
            </OfficerProtectedRoute>
          }
        />
        <Route
          path="/officer/grievances/:grievanceNumber"
          element={
            <OfficerProtectedRoute>
              <OfficerGrievanceDetailPage />
            </OfficerProtectedRoute>
          }
        />
        <Route path="/ai-assistant" element={<ProtectedRoute><CitizenAIAssistantPage /></ProtectedRoute>} />
        <Route path="/officer/ai" element={<OfficerProtectedRoute><OfficerAIPage /></OfficerProtectedRoute>} />
        <Route path="/officer/grievances/:grievanceNumber/ai" element={<OfficerProtectedRoute><OfficerAIPage /></OfficerProtectedRoute>} />
        <Route path="/notifications" element={<ProtectedRoute><NotificationCenterPage /></ProtectedRoute>} />
        <Route path="/notifications/preferences" element={<ProtectedRoute><NotificationPreferencesPage /></ProtectedRoute>} />
        <Route path="/admin/dashboard" element={<AdminProtectedRoute><AdminDashboardPage /></AdminProtectedRoute>} />
        <Route path="/admin/grievances" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/officers" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/departments" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/categories" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/privacy" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/audit" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/ai" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/analytics" element={<AdminProtectedRoute><AdminManagementPage /></AdminProtectedRoute>} />
        <Route path="/admin/projects" element={<AdminProtectedRoute><AdminProjectsPage /></AdminProtectedRoute>} />
        <Route path="/admin/projects/new" element={<AdminProtectedRoute><AdminProjectCreatePage /></AdminProtectedRoute>} />
        <Route path="/admin/projects/:id" element={<AdminProtectedRoute><AdminProjectDetailPage /></AdminProtectedRoute>} />
      </Routes>
    </>
  );
}

export default App;
