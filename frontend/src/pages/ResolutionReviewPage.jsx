import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, FileText } from "lucide-react";
import Alert from "../components/Alert.jsx";
import StatusTimeline from "../components/StatusTimeline.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import {
  acceptResolution,
  disputeResolution,
  downloadResolutionEvidence,
  getGrievance,
  getResolutionReview,
  submitResolutionFeedback,
} from "../services/api.js";

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";
}

function ResolutionReviewPage() {
  const { grievanceNumber } = useParams();
  const { accessToken } = useAuth();
  const [grievance, setGrievance] = useState(null);
  const [review, setReview] = useState(null);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [disputeReason, setDisputeReason] = useState("");
  const [showDispute, setShowDispute] = useState(false);
  const [rating, setRating] = useState("");
  const [feedback, setFeedback] = useState("");

  async function load() {
    if (!accessToken) return;
    try {
      const [g, r] = await Promise.all([getGrievance(grievanceNumber, accessToken), getResolutionReview(grievanceNumber, accessToken)]);
      setGrievance(g);
      setReview(r);
    } catch {
      setError("This resolution could not be loaded.");
    }
  }

  useEffect(() => { load(); }, [accessToken, grievanceNumber]);

  async function handleAccept() {
    if (!window.confirm("Accept this resolution and close the grievance?")) return;
    setBusy(true); setActionError(null);
    try { await acceptResolution(grievanceNumber, accessToken); await load(); }
    catch (err) { setActionError(err.message || "Could not accept the resolution."); }
    finally { setBusy(false); }
  }

  async function handleDispute(event) {
    event.preventDefault();
    if (!disputeReason.trim()) return;
    setBusy(true); setActionError(null);
    try { await disputeResolution(grievanceNumber, disputeReason, accessToken); setDisputeReason(""); setShowDispute(false); await load(); }
    catch (err) { setActionError(err.message || "Could not dispute the resolution."); }
    finally { setBusy(false); }
  }

  async function handleFeedback(event) {
    event.preventDefault();
    setBusy(true); setActionError(null);
    try { await submitResolutionFeedback(grievanceNumber, { rating, feedback }, accessToken); setRating(""); setFeedback(""); await load(); }
    catch (err) { setActionError(err.message || "Could not submit feedback."); }
    finally { setBusy(false); }
  }

  async function handleEvidence(evidence) {
    try {
      const blob = await downloadResolutionEvidence(grievanceNumber, evidence.id, accessToken);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) { setActionError(err.message || "Could not open evidence."); }
  }

  if (error) return <div className="app-shell"><Alert type="error">{error}</Alert><Link to="/complaints">Back to complaints</Link></div>;
  if (!grievance || !review) return <div className="app-shell"><div className="loading-state"><span className="spinner" /> Loading resolution...</div></div>;

  const resolution = review.resolution;
  const awaitingReview = grievance.status === "RESOLVED" && resolution;
  const canFeedback = grievance.status === "RESOLVED" || grievance.status === "CLOSED";

  return (
    <div className="app-shell">
      <header className="app-header">
        <p><Link to={`/complaints/${encodeURIComponent(grievanceNumber)}`}><ArrowLeft size={13} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />Complaint</Link></p>
        <h1><FileText size={20} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Resolution Review</h1>
        <p className="case-id">{grievance.grievance_number}</p>
      </header>

      <Alert type="error">{actionError}</Alert>

      <div className="status-card" style={{ maxWidth: 760, width: "100%", marginBottom: "1.5rem" }}>
        <h2 className="section-heading">Complaint</h2>
        <div className="status-row"><span className="status-label">Title</span><span>{grievance.title}</span></div>
        <div className="status-row"><span className="status-label">Status</span><span>{grievance.status}</span></div>
        <div className="status-row"><span className="status-label">Department</span><span>{grievance.department?.name || "—"}</span></div>
        <p style={{ whiteSpace: "pre-wrap" }}>{grievance.description}</p>
        <StatusTimeline currentStatus={grievance.status} history={grievance.status_history} />
      </div>

      {!resolution ? (
        <div className="status-card" style={{ maxWidth: 760, width: "100%" }}><p>No resolution has been submitted yet.</p></div>
      ) : (
        <div className="status-card" style={{ maxWidth: 760, width: "100%", marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
            <h2 className="section-heading">Officer Resolution</h2>
            <span className="badge pending">{grievance.status === "RESOLVED" ? "AWAITING CITIZEN REVIEW" : resolution.status}</span>
          </div>
          <div className="status-row"><span className="status-label">Resolution date</span><span>{formatDateTime(resolution.resolution_date)}</span></div>
          {resolution.completion_percentage != null && <div className="status-row"><span className="status-label">Completion</span><span>{resolution.completion_percentage}%</span></div>}
          <h3>Summary</h3><p style={{ whiteSpace: "pre-wrap" }}>{resolution.resolution_summary}</p>
          <h3>Actions taken</h3><p style={{ whiteSpace: "pre-wrap" }}>{resolution.actions_taken}</p>
          {resolution.remarks && <><h3>Remarks</h3><p style={{ whiteSpace: "pre-wrap" }}>{resolution.remarks}</p></>}
          {resolution.external_reference && <div className="status-row"><span className="status-label">Reference</span><span>{resolution.external_reference}</span></div>}
          {resolution.evidence.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <h3>Resolution Evidence</h3>
              {resolution.evidence.map((item) => (
                <div className="status-row" key={item.id}>
                  <span>{item.file_name}</span>
                  <button type="button" className="btn-link" onClick={() => handleEvidence(item)}>View</button>
                </div>
              ))}
            </div>
          )}

          {awaitingReview && (
            <div style={{ marginTop: "1.5rem" }}>
              <p><strong>RESOLVED</strong> means the officer submitted a resolution. It is not yet CLOSED.</p>
              <button type="button" className="btn-primary" onClick={handleAccept} disabled={busy}>Accept Resolution</button>{" "}
              <button type="button" className="btn-secondary" onClick={() => setShowDispute((v) => !v)} disabled={busy}>Dispute Resolution</button>
              {showDispute && <form onSubmit={handleDispute} style={{ marginTop: "1rem" }}>
                <label htmlFor="dispute-reason">Why are you disputing this resolution?</label>
                <textarea id="dispute-reason" rows={5} value={disputeReason} onChange={(e) => setDisputeReason(e.target.value)} placeholder="Explain what remains unresolved or why the evidence does not match." />
                <button type="submit" className="btn-primary" disabled={busy || disputeReason.trim().length < 5}>Submit Dispute</button>
              </form>}
            </div>
          )}
        </div>
      )}

      {review.disputes.length > 0 && (
        <div className="status-card" style={{ maxWidth: 760, width: "100%", marginBottom: "1.5rem" }}>
          <h2 className="section-heading">Dispute Submitted</h2>
          {review.disputes.map((d) => <div key={d.id}><p>{d.reason}</p><small>{formatDateTime(d.created_at)}</small></div>)}
          <p>The grievance has returned to officer processing for review.</p>
        </div>
      )}

      {canFeedback && (
        <div className="status-card" style={{ maxWidth: 760, width: "100%" }}>
          <h2 className="section-heading">Optional Feedback</h2>
          <p>Your rating and feedback are optional and do not control closure.</p>
          <form onSubmit={handleFeedback}>
            <label htmlFor="rating">Rating</label>
            <select id="rating" value={rating} onChange={(e) => setRating(e.target.value)}><option value="">No rating</option>{[1,2,3,4,5].map((n) => <option key={n} value={n}>{n}/5</option>)}</select>
            <label htmlFor="feedback">Feedback</label>
            <textarea id="feedback" rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
            <button type="submit" className="btn-primary" disabled={busy || (!rating && !feedback.trim())}>Submit Feedback</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default ResolutionReviewPage;
