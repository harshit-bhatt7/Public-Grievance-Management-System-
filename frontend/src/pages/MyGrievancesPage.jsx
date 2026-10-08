import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FilePlus2, Inbox } from "lucide-react";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getMyGrievances } from "../services/api.js";

function StatusBadge({ status }) {
  const className = `badge status-${(status || "").toLowerCase()}`;
  return <span className={className}>{(status || "").replace(/_/g, " ")}</span>;
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

function MyGrievancesPage() {
  const { accessToken } = useAuth();
  const [grievances, setGrievances] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!accessToken) return;
    getMyGrievances(accessToken)
      .then(setGrievances)
      .catch(() => setError("Could not load your complaints. Please try again."));
  }, [accessToken]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>My Complaints</h1>
        <p>
          <Link to="/complaints/new">
            <FilePlus2 size={14} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
            File a new complaint
          </Link>
        </p>
      </header>

      <Alert type="error">{error}</Alert>

      {grievances === null && !error && (
        <div className="loading-state">
          <span className="spinner" /> Loading your complaints...
        </div>
      )}

      {grievances && grievances.length === 0 && (
        <div className="empty-state">
          <Inbox size={30} className="empty-state-icon" />
          <h3>No grievances found</h3>
          <p>You haven't filed any complaints yet. When you do, they'll show up here with live status updates.</p>
          <Link className="btn-primary" to="/complaints/new" style={{ display: "inline-flex", width: "auto", marginTop: "0.5rem" }}>
            File your first complaint
          </Link>
        </div>
      )}

      {grievances && grievances.length > 0 && (
        <div className="status-card" style={{ maxWidth: 640, width: "100%" }}>
          {grievances.map((grievance) => (
            <Link
              to={`/complaints/${encodeURIComponent(grievance.grievance_number)}`}
              className="status-row grievance-row"
              key={grievance.grievance_number}
            >
              <div>
                <div>
                  <strong>{grievance.grievance_number}</strong> — {grievance.title}
                </div>
                <div className="status-label">
                  {grievance.category.name}
                  {grievance.department ? ` · ${grievance.department.name}` : ""} · Submitted{" "}
                  {formatDate(grievance.submitted_at)} · Updated{" "}
                  {formatDate(grievance.updated_at)}
                </div>
              </div>
              <StatusBadge status={grievance.status} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export default MyGrievancesPage;
