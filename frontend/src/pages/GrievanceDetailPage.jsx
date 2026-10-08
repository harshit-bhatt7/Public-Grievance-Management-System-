import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileCheck2, Lock, Paperclip } from "lucide-react";
import Alert from "../components/Alert.jsx";
import StatusTimeline from "../components/StatusTimeline.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { ApiError, getGrievance, updateGrievancePrivacy } from "../services/api.js";

function StatusBadge({ status }) {
  const className = `badge status-${(status || "").toLowerCase()}`;
  return <span className={className}>{(status || "").replace(/_/g, " ")}</span>;
}

const PRIVACY_LABELS = {
  NORMAL: "Normal",
  CONFIDENTIAL: "Confidential",
  IDENTITY_PROTECTED: "Identity Protected",
};

const PRIVACY_OPTIONS = [
  { value: "NORMAL", label: "Normal", description: "Your identity may be visible to authorized staff when required." },
  { value: "CONFIDENTIAL", label: "Confidential", description: "Your personal information is restricted to the minimum required." },
  { value: "IDENTITY_PROTECTED", label: "Identity Protected", description: "Your identity is hidden unless authorized access is approved." },
];

function formatDateTime(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function GrievanceDetailPage() {
  const { grievanceNumber } = useParams();
  const { accessToken } = useAuth();

  const [grievance, setGrievance] = useState(null);
  const [error, setError] = useState(null);
  const [editingPrivacy, setEditingPrivacy] = useState(false);
  const [privacySaving, setPrivacySaving] = useState(false);
  const [privacyError, setPrivacyError] = useState(null);

  useEffect(() => {
    if (!accessToken) return;
    getGrievance(grievanceNumber, accessToken)
      .then(setGrievance)
      .catch(() => setError("This complaint could not be found."));
  }, [accessToken, grievanceNumber]);

  async function handlePrivacyChange(newMode) {
    setPrivacySaving(true);
    setPrivacyError(null);
    try {
      const updated = await updateGrievancePrivacy(grievanceNumber, newMode, accessToken);
      setGrievance(updated);
      setEditingPrivacy(false);
    } catch (err) {
      setPrivacyError(err instanceof ApiError ? err.message : "Could not update privacy setting.");
    } finally {
      setPrivacySaving(false);
    }
  }

  if (error) {
    return (
      <div className="app-shell">
        <Alert type="error">{error}</Alert>
        <p className="footer-note">
          <Link to="/complaints">Back to my complaints</Link>
        </p>
      </div>
    );
  }

  if (!grievance) {
    return (
      <div className="app-shell">
        <div className="loading-state">
          <span className="spinner" /> Loading complaint...
        </div>
      </div>
    );
  }

  const location = [grievance.address, grievance.city, grievance.state, grievance.pincode]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="app-shell">
      <header className="app-header" style={{ textAlign: "left" }}>
        <p>
          <Link to="/complaints">
            <ArrowLeft size={13} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
            My Complaints
          </Link>
        </p>
        <div className="case-header">
          <div>
            <h1 style={{ marginBottom: "0.25rem" }}>{grievance.title}</h1>
            <span className="case-id">{grievance.grievance_number}</span>
          </div>
          <StatusBadge status={grievance.status} />
        </div>
      </header>

      {(grievance.status === "RESOLVED" || grievance.status === "CLOSED") && (
        <p style={{ marginBottom: "1rem" }}>
          <Link to={`/complaints/${encodeURIComponent(grievanceNumber)}/resolution`}>
            <FileCheck2 size={14} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
            Review resolution
          </Link>
        </p>
      )}

      <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
        <h2 className="section-heading">Complaint Information</h2>
        <div className="status-row">
          <span className="status-label">Category</span>
          <span>{grievance.category.name}</span>
        </div>
        {grievance.department && (
          <div className="status-row">
            <span className="status-label">Department</span>
            <span>{grievance.department.name}</span>
          </div>
        )}
        {grievance.routing_type && (
          <div className="status-row">
            <span className="status-label">Routing</span>
            <span>{grievance.routing_type === "AUTOMATIC" ? "Automatically assigned" : "Manually assigned"}</span>
          </div>
        )}
        <div className="status-row">
          <span className="status-label">Description</span>
          <span style={{ maxWidth: "60%", textAlign: "right" }}>{grievance.description}</span>
        </div>
        {location && (
          <div className="status-row">
            <span className="status-label">Location</span>
            <span style={{ maxWidth: "60%", textAlign: "right" }}>{location}</span>
          </div>
        )}
        <div className="status-row">
          <span className="status-label">Submitted</span>
          <span>{formatDateTime(grievance.submitted_at)}</span>
        </div>
        <div className="status-row">
          <span className="status-label">Last Updated</span>
          <span>{formatDateTime(grievance.updated_at)}</span>
        </div>
        <div className="status-row">
          <span className="status-label">Current Status</span>
          <StatusBadge status={grievance.status} />
        </div>
      </div>

      <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
        <h2 className="section-heading"><Lock size={16} />Privacy</h2>
        <Alert type="error">{privacyError}</Alert>

        {!editingPrivacy ? (
          <div className="status-row">
            <span className="status-label">{PRIVACY_LABELS[grievance.privacy_mode] || grievance.privacy_mode}</span>
            <button type="button" className="btn-link" onClick={() => setEditingPrivacy(true)}>
              Change
            </button>
          </div>
        ) : (
          <div className="privacy-options">
            {PRIVACY_OPTIONS.map((option) => (
              <label key={option.value} className="privacy-option">
                <input
                  type="radio"
                  name="privacy_mode_edit"
                  value={option.value}
                  checked={grievance.privacy_mode === option.value}
                  disabled={privacySaving}
                  onChange={() => handlePrivacyChange(option.value)}
                />
                <span>
                  <strong>{option.label}</strong>
                  <span className="privacy-option-description">{option.description}</span>
                </span>
              </label>
            ))}
            <button type="button" className="btn-link" onClick={() => setEditingPrivacy(false)} disabled={privacySaving}>
              Cancel
            </button>
          </div>
        )}
      </div>

      {grievance.attachments.length > 0 && (
        <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
          <h2 className="section-heading"><Paperclip size={16} />Evidence</h2>
          {grievance.attachments.map((attachment) => (
            <div className="status-row" key={attachment.id}>
              <span>{attachment.file_name}</span>
              <span className="status-label">{Math.round(attachment.file_size / 1024)} KB</span>
            </div>
          ))}
        </div>
      )}

      <div className="status-card" style={{ maxWidth: 640, width: "100%" }}>
        <h2 className="section-heading">Status Timeline</h2>
        <StatusTimeline currentStatus={grievance.status} history={grievance.status_history} />
      </div>
    </div>
  );
}

export default GrievanceDetailPage;
