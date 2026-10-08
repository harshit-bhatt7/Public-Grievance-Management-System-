import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList, Inbox, LayoutDashboard } from "lucide-react";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getOfficerDashboard } from "../services/api.js";

function StatCard({ label, value }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function StatusBadge({ status }) {
  const className = `badge status-${(status || "").toLowerCase()}`;
  return <span className={className}>{(status || "").replace(/_/g, " ")}</span>;
}

function OfficerDashboardPage() {
  const { accessToken } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!accessToken) return;
    getOfficerDashboard(accessToken)
      .then(setDashboard)
      .catch((err) => setError(err.message || "Could not load the dashboard."));
  }, [accessToken]);

  if (error) {
    return (
      <div className="app-shell">
        <Alert type="error">{error}</Alert>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="app-shell">
        <div className="loading-state">
          <span className="spinner" /> Loading your department's operational dashboard...
        </div>
      </div>
    );
  }

  const { stats } = dashboard;

  return (
    <div className="app-shell">
      <header className="app-header" style={{ textAlign: "left" }}>
        <span className="badge neutral" style={{ marginBottom: "0.6rem" }}>
          <LayoutDashboard size={13} /> Officer Workspace
        </span>
        <h1>Officer Dashboard</h1>
        <p>{dashboard.department.name}</p>
        <p className="footer-note" style={{ margin: "0.5rem 0 0", textAlign: "left" }}>
          <Link to="/officer/grievances">
            <ClipboardList size={13} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
            View all department grievances
          </Link>
        </p>
      </header>

      <div className="stat-grid">
        <StatCard label="Total" value={stats.total} />
        <StatCard label="Submitted" value={stats.submitted} />
        <StatCard label="Under Review" value={stats.under_review} />
        <StatCard label="Assigned" value={stats.assigned} />
        <StatCard label="In Progress" value={stats.in_progress} />
        <StatCard label="Resolved" value={stats.resolved} />
        <StatCard label="Rejected" value={stats.rejected} />
        <StatCard label="Closed" value={stats.closed} />
      </div>

      <div className="status-card" style={{ maxWidth: 640, width: "100%", marginTop: "1.5rem" }}>
        <h2 className="section-heading">Recent Grievances</h2>
        {dashboard.recent_grievances.length === 0 && (
          <div className="empty-state">
            <Inbox size={28} className="empty-state-icon" />
            <p style={{ margin: 0 }}>No grievances yet for your department.</p>
          </div>
        )}
        {dashboard.recent_grievances.map((grievance) => (
          <Link
            to={`/officer/grievances/${encodeURIComponent(grievance.grievance_number)}`}
            className="status-row grievance-row"
            key={grievance.grievance_number}
          >
            <div>
              <div>
                <strong>{grievance.grievance_number}</strong> — {grievance.title}
              </div>
              <div className="status-label">{grievance.category.name}</div>
            </div>
            <StatusBadge status={grievance.status} />
          </Link>
        ))}
      </div>
    </div>
  );
}

export default OfficerDashboardPage;
