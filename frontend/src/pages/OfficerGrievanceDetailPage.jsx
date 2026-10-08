import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, BrainCircuit, Layers, Paperclip, UserRound } from "lucide-react";
import Alert from "../components/Alert.jsx";
import StatusTimeline from "../components/StatusTimeline.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { ApiError, claimGrievance, getOfficerGrievanceDetail, updateGrievanceStatusAsOfficer, getOfficerResolutions, submitOfficerResolution, downloadResolutionEvidence, getOfficerPossibleMatches, reviewExistingWorkMatch } from "../services/api.js";

function StatusBadge({ status }) {
  const className = `badge status-${(status || "").toLowerCase()}`;
  return <span className={className}>{(status || "").replace(/_/g, " ")}</span>;
}

const NEXT_STATUS_OPTIONS = {
  SUBMITTED: ["UNDER_REVIEW"],
  UNDER_REVIEW: ["ASSIGNED", "REJECTED"],
  ASSIGNED: ["IN_PROGRESS"],
  IN_PROGRESS: ["RESOLVED"],
  RESOLVED: ["CLOSED"],
  REJECTED: [],
  CLOSED: [],
};

function formatDateTime(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function OfficerGrievanceDetailPage() {
  const { grievanceNumber } = useParams();
  const { accessToken } = useAuth();

  const [grievance, setGrievance] = useState(null);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [remarks, setRemarks] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [resolutions, setResolutions] = useState([]);
  const [resolutionForm, setResolutionForm] = useState({ resolution_summary: "", actions_taken: "", resolution_date: new Date().toISOString().slice(0, 16), remarks: "", completion_percentage: "", external_reference: "" });
  const [resolutionFiles, setResolutionFiles] = useState([]);
  const [possibleMatches, setPossibleMatches] = useState([]);
  const [matchReviewing, setMatchReviewing] = useState(null);

  function load() {
    Promise.all([
      getOfficerGrievanceDetail(grievanceNumber, accessToken),
      getOfficerResolutions(grievanceNumber, accessToken),
      getOfficerPossibleMatches(grievanceNumber, accessToken),
    ])
      .then(([g, r, m]) => { setGrievance(g); setResolutions(r); setPossibleMatches(m.matches || []); })
      .catch(() => setError("This grievance could not be found or is not in your department."));
  }

  useEffect(() => {
    if (!accessToken) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, grievanceNumber]);

  async function handleClaim() {
    setSubmitting(true);
    setActionError(null);
    try {
      await claimGrievance(grievanceNumber, accessToken);
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not claim this grievance.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusUpdate(event) {
    event.preventDefault();
    if (!selectedStatus) return;
    setSubmitting(true);
    setActionError(null);
    try {
      const updated = await updateGrievanceStatusAsOfficer(grievanceNumber, selectedStatus, remarks, accessToken);
      setGrievance(updated);
      setRemarks("");
      setSelectedStatus("");
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not update status.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResolutionSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setActionError(null);
    try {
      await submitOfficerResolution(grievanceNumber, resolutionForm, resolutionFiles, accessToken);
      setResolutionForm({ resolution_summary: "", actions_taken: "", resolution_date: new Date().toISOString().slice(0, 16), remarks: "", completion_percentage: "", external_reference: "" });
      setResolutionFiles([]);
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not submit resolution.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEvidence(evidence) {
    try {
      const blob = await downloadResolutionEvidence(grievanceNumber, evidence.id, accessToken, true);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not open evidence.");
    }
  }

  async function handleMatchReview(matchId, state) {
    setMatchReviewing(matchId);
    try {
      await reviewExistingWorkMatch(matchId, state, accessToken);
      setPossibleMatches((prev) => prev.map((m) => m.id === matchId ? {...m, review_state:state} : m));
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Could not review the existing-work match.");
    } finally {
      setMatchReviewing(null);
    }
  }

  if (error) {
    return (
      <div className="app-shell">
        <Alert type="error">{error}</Alert>
        <p className="footer-note">
          <Link to="/officer/grievances">Back to grievances</Link>
        </p>
      </div>
    );
  }

  if (!grievance) {
    return (
      <div className="app-shell">
        <div className="loading-state">
          <span className="spinner" /> Loading grievance...
        </div>
      </div>
    );
  }

  const nextOptions = (NEXT_STATUS_OPTIONS[grievance.status] || []).filter((s) => s !== "CLOSED");

  return (
    <div className="app-shell">
      <header className="app-header" style={{ textAlign: "left" }}>
        <p>
          <Link to="/officer/grievances">
            <ArrowLeft size={13} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
            Department Grievances
          </Link>
        </p>
        <div className="case-header">
          <div>
            <h1 style={{ marginBottom: "0.25rem" }}>{grievance.title}</h1>
            <span className="case-id">{grievance.grievance_number}</span>
          </div>
          <StatusBadge status={grievance.status} />
        </div>
        <p style={{ marginTop: "0.75rem" }}>
          <Link to={`/officer/grievances/${encodeURIComponent(grievanceNumber)}/ai`} className="btn-outline" style={{ display: "inline-flex" }}>
            <BrainCircuit size={14} /> AI Tools
          </Link>
        </p>
      </header>

      <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
        <h2 className="section-heading">Complaint Information</h2>
        <div className="status-row">
          <span className="status-label">Category</span>
          <span>{grievance.category.name}</span>
        </div>
        <div className="status-row">
          <span className="status-label">Department</span>
          <span>{grievance.department ? grievance.department.name : ""}</span>
        </div>
        <div className="status-row">
          <span className="status-label">Description</span>
          <span style={{ maxWidth: "60%", textAlign: "right" }}>{grievance.description}</span>
        </div>
        {(grievance.city || grievance.state) && (
          <div className="status-row">
            <span className="status-label">Location</span>
            <span>{[grievance.city, grievance.state].filter(Boolean).join(", ")}</span>
          </div>
        )}
        <div className="status-row">
          <span className="status-label">Privacy Mode</span>
          <span className="badge neutral">{grievance.privacy_mode.replace(/_/g, " ")}</span>
        </div>
        <div className="status-row">
          <span className="status-label">Submitted</span>
          <span>{formatDateTime(grievance.submitted_at)}</span>
        </div>
        <div className="status-row">
          <span className="status-label">Last Updated</span>
          <span>{formatDateTime(grievance.updated_at)}</span>
        </div>
        {grievance.contact_name && (
          <div className="status-row">
            <span className="status-label"><UserRound size={14} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />Citizen</span>
            <span>{grievance.contact_name}</span>
          </div>
        )}
        {grievance.contact_phone_masked && (
          <div className="status-row">
            <span className="status-label">Phone</span>
            <span>{grievance.contact_phone_masked}</span>
          </div>
        )}
        {grievance.contact_email_masked && (
          <div className="status-row">
            <span className="status-label">Email</span>
            <span>{grievance.contact_email_masked}</span>
          </div>
        )}
      </div>

      {possibleMatches.length > 0 && (
        <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
          <h2 className="section-heading"><Layers size={16} />Possible Existing Work</h2>
          <p className="auth-subtitle">These are reviewable suggestions only. No grievance is automatically merged.</p>
          <div style={{ display: "grid", gap: "1rem" }}>
            {possibleMatches.slice(0, 10).map((match) => {
              const d = match.details || {};
              return (
                <div key={match.id} className="match-card">
                  <div className="match-card-head">
                    <strong>{d.name || d.title}</strong>
                    <span className="badge pending">{Math.round(match.confidence_score)}% match</span>
                  </div>
                  <div className="status-row"><span className="status-label">Type</span><span>{match.match_type}</span></div>
                  <div className="status-row"><span className="status-label">Status</span><span>{d.status}</span></div>
                  <div className="status-row"><span className="status-label">Department</span><span>{d.department || "—"}</span></div>
                  {(match.match_reason || []).length > 0 && <ul className="match-reasons">{(match.match_reason || []).map((r) => <li key={r}>{r}</li>)}</ul>}
                  {match.id && (
                    <div style={{ display:"flex", gap:"0.75rem", marginTop: "0.75rem" }}>
                      <button type="button" className="btn-primary" disabled={matchReviewing === match.id} onClick={() => handleMatchReview(match.id, "CONFIRMED")}>Confirm Related</button>
                      <button type="button" className="btn-outline" disabled={matchReviewing === match.id} onClick={() => handleMatchReview(match.id, "REJECTED")}>Not Related</button>
                    </div>
                  )}
                  <p className="auth-subtitle" style={{ marginTop: "0.6rem", marginBottom: 0 }}>Review: <span className="badge neutral">{(match.review_state || "PENDING_REVIEW").replace(/_/g, " ")}</span></p>
                </div>
              );
            })}
          </div>
        </div>
      )}

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

      <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
        <h2 className="section-heading">Process Complaint</h2>
        <Alert type="error">{actionError}</Alert>

        <button type="button" className="btn-secondary" onClick={handleClaim} disabled={submitting} style={{ marginBottom: "1rem" }}>
          Claim Complaint
        </button>

        {nextOptions.length > 0 && (
          <form onSubmit={handleStatusUpdate}>
            <div className="form-field">
              <label htmlFor="next-status">Update Status</label>
              <select id="next-status" value={selectedStatus} onChange={(e) => setSelectedStatus(e.target.value)}>
                <option value="">Select next status</option>
                {nextOptions.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="remarks">Remarks</label>
              <textarea
                id="remarks"
                rows={3}
                value={remarks}
                onChange={(e) => setRemarks(e.target.value)}
                placeholder="e.g. Repair team assigned to inspect the location."
              />
            </div>
            <button type="submit" className="btn-primary" disabled={submitting || !selectedStatus}>
              Update Status
            </button>
          </form>
        )}
      </div>

      <div className="status-card" style={{ maxWidth: 640, width: "100%", marginBottom: "1.5rem" }}>
        <h2 className="section-heading">Resolution Workflow</h2>
        {resolutions.length > 0 && resolutions.map((resolution) => (
          <div key={resolution.id} style={{ borderTop: "1px solid var(--color-border)", paddingTop: "1rem", marginTop: "1rem" }}>
            <strong>Resolution submitted {formatDateTime(resolution.created_at)}</strong>
            <p style={{ whiteSpace: "pre-wrap" }}>{resolution.resolution_summary}</p>
            {resolution.disputes?.length > 0 && resolution.disputes.map((d) => <Alert type="warning" key={d.id}><strong>Citizen dispute:</strong> {d.reason}</Alert>)}
            {resolution.evidence?.map((item) => <div className="status-row" key={item.id}><span>{item.file_name}</span><button type="button" className="btn-link" onClick={() => handleEvidence(item)}>View</button></div>)}
          </div>
        ))}
        {grievance.status === "IN_PROGRESS" && (
          <form onSubmit={handleResolutionSubmit} style={{ marginTop: "1.25rem" }}>
            <div className="form-field"><label>Resolution summary</label><textarea rows={4} value={resolutionForm.resolution_summary} onChange={(e) => setResolutionForm({ ...resolutionForm, resolution_summary: e.target.value })} required /></div>
            <div className="form-field"><label>Actions taken</label><textarea rows={4} value={resolutionForm.actions_taken} onChange={(e) => setResolutionForm({ ...resolutionForm, actions_taken: e.target.value })} required /></div>
            <div className="form-field"><label>Resolution date</label><input type="datetime-local" value={resolutionForm.resolution_date} onChange={(e) => setResolutionForm({ ...resolutionForm, resolution_date: e.target.value })} required /></div>
            <div className="form-field"><label>Remarks</label><textarea rows={3} value={resolutionForm.remarks} onChange={(e) => setResolutionForm({ ...resolutionForm, remarks: e.target.value })} /></div>
            <div className="form-field"><label>Completion percentage</label><input type="number" min="0" max="100" value={resolutionForm.completion_percentage} onChange={(e) => setResolutionForm({ ...resolutionForm, completion_percentage: e.target.value })} /></div>
            <div className="form-field"><label>External/reference document</label><input value={resolutionForm.external_reference} onChange={(e) => setResolutionForm({ ...resolutionForm, external_reference: e.target.value })} /></div>
            <div className="form-field"><label>Evidence</label><input type="file" accept=".jpg,.jpeg,.png,.pdf" multiple onChange={(e) => setResolutionFiles(Array.from(e.target.files || []))} /></div>
            <button type="submit" className="btn-primary" disabled={submitting || !resolutionForm.resolution_summary.trim() || !resolutionForm.actions_taken.trim()}>Submit Resolution for Citizen Review</button>
          </form>
        )}
        {grievance.status === "RESOLVED" && <p style={{ marginTop: "1rem" }}>Waiting for the citizen to accept or dispute this resolution. <strong>RESOLVED is not CLOSED.</strong></p>}
      </div>

      <div className="status-card" style={{ maxWidth: 640, width: "100%" }}>
        <h2 className="section-heading">Status Timeline</h2>
        <StatusTimeline currentStatus={grievance.status} history={grievance.status_history} />
      </div>
    </div>
  );
}

export default OfficerGrievanceDetailPage;
