import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ClipboardX } from "lucide-react";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getOfficerGrievances } from "../services/api.js";

const STATUS_OPTIONS = ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "REJECTED", "CLOSED"];

function StatusBadge({ status }) {
  const className = `badge status-${(status || "").toLowerCase()}`;
  return <span className={className}>{(status || "").replace(/_/g, " ")}</span>;
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString();
}

function OfficerGrievanceListPage() {
  const { accessToken } = useAuth();
  const [grievances, setGrievances] = useState(null);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    if (!accessToken) return;
    // Server-side filtering — the backend applies the department
    // restriction and any status/search filters; nothing is filtered here.
    getOfficerGrievances(accessToken, {
      status: statusFilter || undefined,
      grievance_number: searchTerm || undefined,
    })
      .then(setGrievances)
      .catch((err) => setError(err.message || "Could not load grievances."));
  }, [accessToken, statusFilter, searchTerm]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Department Grievances</h1>
        <p>
          <Link to="/officer/dashboard">
            <ArrowLeft size={13} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
            Dashboard
          </Link>
        </p>
      </header>

      <div className="filter-bar">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search grievance number"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          aria-label="Search grievance number"
        />
      </div>

      <Alert type="error">{error}</Alert>

      {grievances === null && !error && (
        <div className="loading-state"><span className="spinner" /> Loading grievances...</div>
      )}
      {grievances && grievances.length === 0 && (
        <div className="empty-state">
          <ClipboardX size={28} className="empty-state-icon" />
          <h3>No matching grievances</h3>
          <p>Try clearing the status filter or search term.</p>
        </div>
      )}

      {grievances && grievances.length > 0 && (
        <div className="status-card" style={{ maxWidth: 720, width: "100%" }}>
          {grievances.map((grievance) => (
            <Link
              to={`/officer/grievances/${encodeURIComponent(grievance.grievance_number)}`}
              className="status-row grievance-row"
              key={grievance.grievance_number}
            >
              <div>
                <div>
                  <strong>{grievance.grievance_number}</strong> — {grievance.title}
                </div>
                <div className="status-label">
                  {grievance.category.name} · Submitted {formatDate(grievance.submitted_at)}
                  {grievance.is_claimed && (grievance.claimed_by_me ? " · Claimed by you" : " · Claimed")}
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

export default OfficerGrievanceListPage;
