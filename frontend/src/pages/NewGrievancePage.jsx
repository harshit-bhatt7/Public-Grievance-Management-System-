import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  MessageSquareText,
  Tag,
  MapPin,
  Paperclip,
  Lock,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Eye,
} from "lucide-react";
import FormField from "../components/FormField.jsx";
import Alert from "../components/Alert.jsx";
import VoiceComplaintButton from "../components/VoiceComplaintButton.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { ApiError, createGrievance, getCategories, uploadAttachment, checkExistingWork, recordExistingWorkAction, followProject } from "../services/api.js";
import {
  validateAttachmentFile,
  validateCategory,
  validateGrievanceDescription,
  validateGrievanceTitle,
  validateLatitude,
  validateLongitude,
  validatePincode,
} from "../utils/validation.js";

const initialForm = {
  title: "",
  category_id: "",
  description: "",
  address: "",
  city: "",
  district: "",
  taluka: "",
  village: "",
  state: "",
  pincode: "",
  latitude: "",
  longitude: "",
  privacy_mode: "IDENTITY_PROTECTED",
};

const PRIVACY_OPTIONS = [
  {
    value: "NORMAL",
    label: "Normal",
    description: "Your identity may be visible to authorized staff when required to process the complaint.",
  },
  {
    value: "CONFIDENTIAL",
    label: "Confidential",
    description: "Your personal information is restricted to the minimum required.",
  },
  {
    value: "IDENTITY_PROTECTED",
    label: "Identity Protected",
    description: "Your identity is hidden from ordinary officers unless authorized access is approved.",
  },
];

function NewGrievancePage() {
  const { accessToken } = useAuth();

  const [categories, setCategories] = useState([]);
  const [categoriesError, setCategoriesError] = useState(null);

  const [form, setForm] = useState(initialForm);
  const [files, setFiles] = useState([]);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // holds the created grievance on success
  const [attachmentWarning, setAttachmentWarning] = useState(null);
  const [existingWork, setExistingWork] = useState(null);
  const [checkingExistingWork, setCheckingExistingWork] = useState(false);
  const [followingMatch, setFollowingMatch] = useState(null);

  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => setCategoriesError("Could not load categories. Please refresh the page."));
  }, []);

  function handleChange(event) {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function handleFileChange(event) {
    const selected = Array.from(event.target.files || []);
    const fileError = selected.map(validateAttachmentFile).find(Boolean);
    if (fileError) {
      setFieldErrors((prev) => ({ ...prev, files: fileError }));
      setFiles([]);
      event.target.value = "";
      return;
    }
    setFieldErrors((prev) => ({ ...prev, files: null }));
    setFiles(selected);
  }

  function validate() {
    const errors = {
      title: validateGrievanceTitle(form.title),
      category_id: validateCategory(form.category_id),
      description: validateGrievanceDescription(form.description),
      pincode: validatePincode(form.pincode),
      latitude: validateLatitude(form.latitude),
      longitude: validateLongitude(form.longitude),
    };
    setFieldErrors((prev) => ({ ...prev, ...errors }));
    return Object.values(errors).every((error) => !error);
  }

  async function createComplaint(existingMatch = null) {
    setSubmitting(true);
    setFormError(null);
    try {
      const payload = {
        title: form.title.trim(),
        category_id: form.category_id,
        description: form.description.trim(),
        address: form.address.trim() || null,
        city: form.city.trim() || null,
        district: form.district.trim() || null,
        taluka: form.taluka.trim() || null,
        village: form.village.trim() || null,
        state: form.state.trim() || null,
        pincode: form.pincode.trim() || null,
        latitude: form.latitude === "" ? null : Number(form.latitude),
        longitude: form.longitude === "" ? null : Number(form.longitude),
        privacy_mode: form.privacy_mode,
      };

      const grievance = await createGrievance(payload, accessToken);

      if (existingMatch?.matches?.length) {
        const matchIds = existingMatch.matches.map((m) => m.id).filter(Boolean);
        if (matchIds.length) {
          await recordExistingWorkAction(grievance.grievance_number, "SUBMITTED_ANYWAY", matchIds, accessToken);
        }
      }

      if (files.length > 0) {
        for (const file of files) {
          try {
            // eslint-disable-next-line no-await-in-loop
            await uploadAttachment(grievance.grievance_number, file, accessToken);
          } catch {
            setAttachmentWarning(
              "Your complaint was submitted, but one or more attachments failed to upload. You can try again later."
            );
          }
        }
      }

      setResult(grievance);
      setExistingWork(null);
      setForm(initialForm);
      setFiles([]);
    } catch (error) {
      if (error instanceof ApiError) setFormError(error.message);
      else setFormError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError(null);
    setAttachmentWarning(null);
    if (!validate()) return;

    setCheckingExistingWork(true);
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description.trim(),
        category_id: form.category_id,
        city: form.city.trim() || null,
        district: form.district.trim() || null,
        taluka: form.taluka.trim() || null,
        village: form.village.trim() || null,
        state: form.state.trim() || null,
        latitude: form.latitude === "" ? null : Number(form.latitude),
        longitude: form.longitude === "" ? null : Number(form.longitude),
      };
      const analysis = await checkExistingWork(payload, accessToken);
      if (analysis.level !== "NO_MATCH" && analysis.matches?.length) {
        setExistingWork(analysis);
        return;
      }
      await createComplaint(null);
    } catch (error) {
      // Existing-work intelligence is advisory. If its check is unavailable,
      // never block the citizen's complaint submission.
      if (error instanceof ApiError) {
        setFormError("We could not check for existing work, so you can continue with your complaint.");
      }
      await createComplaint(null);
    } finally {
      setCheckingExistingWork(false);
    }
  }

  async function handleSubmitAnyway() {
    await createComplaint(existingWork);
  }

  async function handleFollow(match) {
    if (match.match_type !== "PROJECT" || !match.details?.id) return;
    setFollowingMatch(match.id);
    try {
      await followProject(match.details.id, accessToken);
      setExistingWork((prev) => prev ? {
        ...prev,
        matches: prev.matches.map((m) => m.id === match.id ? {...m, citizen_action:"FOLLOWED"} : m)
      } : prev);
    } finally {
      setFollowingMatch(null);
    }
  }
  if (result) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <span className="badge ok" style={{ marginBottom: "0.9rem" }}>
            <CheckCircle2 size={13} /> Submitted
          </span>
          <h1>Complaint Submitted Successfully</h1>
          <Alert type="success">Your grievance has been recorded.</Alert>
          <Alert type="error">{attachmentWarning}</Alert>

          <div className="status-card" style={{ margin: "1rem 0" }}>
            <div className="status-row">
              <span className="status-label">Grievance Number</span>
              <strong>{result.grievance_number}</strong>
            </div>
            <div className="status-row">
              <span className="status-label">Category</span>
              <span>{result.category.name}</span>
            </div>
            <div className="status-row">
              <span className="status-label">Status</span>
              <span className="badge ok">{result.status}</span>
            </div>
            <div className="status-row">
              <span className="status-label">Privacy</span>
              <span>{PRIVACY_OPTIONS.find((o) => o.value === result.privacy_mode)?.label || result.privacy_mode}</span>
            </div>
            <div className="status-row">
              <span className="status-label">Submitted</span>
              <span>{new Date(result.submitted_at).toLocaleString()}</span>
            </div>
          </div>

          <p className="auth-switch">
            <Link to="/complaints">View my complaints</Link>
          </p>
        </div>
      </div>
    );
  }

  if (existingWork) {
    return (
      <div className="auth-page">
        <div className="auth-card" style={{ maxWidth: 780 }}>
          <div className="existing-work-banner">
            <AlertTriangle size={20} />
            <span>Possible Existing Work — we found work that may already address this issue.</span>
          </div>
          <Alert type="error">{existingWork.message}</Alert>
          <p className="auth-subtitle">
            This is only a recommendation. <strong>You can still submit your complaint</strong> — nothing is
            merged or blocked automatically.
          </p>

          <div style={{ display:"grid", gap:"1rem" }}>
            {existingWork.matches.map((match, index) => {
              const d = match.details || {};
              return (
                <div key={match.id || `${match.match_type}-${index}`} className="match-card">
                  <div className="match-card-head">
                    <div>
                      <span className="status-label">Match {index + 1} · {match.match_type === "PROJECT" ? "Government Project" : "Grievance"}</span>
                      <h3 style={{ margin: "0.2rem 0 0" }}>{match.match_type === "PROJECT" ? d.name : d.title}</h3>
                    </div>
                    <span className={`badge ${match.level === "STRONG_MATCH" ? "error" : "pending"}`}>
                      {Math.round(match.confidence_score)}% match
                    </span>
                  </div>
                  <div className="status-row"><span className="status-label">Status</span><span>{d.status}</span></div>
                  <div className="status-row"><span className="status-label">Category</span><span>{d.category || "—"}</span></div>
                  <div className="status-row"><span className="status-label">Department</span><span>{d.department || "—"}</span></div>
                  {match.match_type === "PROJECT" && (
                    <>
                      <div className="status-row"><span className="status-label">Progress</span><span>{d.progress ?? 0}%</span></div>
                      <div className="progress"><i style={{ width: `${d.progress ?? 0}%` }} /></div>
                      <div className="status-row"><span className="status-label">Related complaints</span><span>{d.related_grievances ?? 0}</span></div>
                      <div className="status-row"><span className="status-label">Expected completion</span><span>{d.expected_completion || "—"}</span></div>
                    </>
                  )}
                  {match.match_type === "GRIEVANCE" && (
                    <div className="status-row"><span className="status-label">Grievance</span><span>{d.grievance_number}</span></div>
                  )}
                  {(match.match_reason || []).length > 0 && (
                    <div style={{ marginTop:"0.85rem" }}>
                      <strong style={{ fontSize: "0.85rem" }}>Why this may match</strong>
                      <ul className="match-reasons">{(match.match_reason || []).map((reason) => <li key={reason}>{reason}</li>)}</ul>
                    </div>
                  )}
                  <div style={{ display:"flex", gap:"0.75rem", flexWrap:"wrap", marginTop:"1rem" }}>
                    {match.match_type === "PROJECT" && (
                      <>
                        <Link className="btn-outline" to={`/projects/${d.id}`}>
                          <ExternalLink size={14} /> View Existing Work
                        </Link>
                        <button type="button" className="btn-secondary" onClick={() => handleFollow(match)} disabled={followingMatch === match.id}>
                          {followingMatch === match.id ? "Following..." : match.citizen_action === "FOLLOWED" ? "Following ✓" : "Follow"}
                        </button>
                      </>
                    )}
                    {match.match_type === "GRIEVANCE" && <span className="auth-subtitle" style={{ margin: 0 }}>Existing grievance status is shown above; private citizen information is not exposed.</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ display:"flex", gap:"0.75rem", flexWrap:"wrap", marginTop:"1.5rem" }}>
            <button type="button" className="btn-primary" onClick={handleSubmitAnyway} disabled={submitting}>
              {submitting ? "Submitting..." : "Submit My Complaint Anyway"}
            </button>
            <button type="button" className="btn-outline" onClick={() => setExistingWork(null)} disabled={submitting}>
              Go Back
            </button>
          </div>
          <p className="auth-subtitle" style={{ marginTop:"1rem" }}>
            You may submit a new complaint if the existing work does not address your issue.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: 640 }}>
        <h1>File a New Complaint</h1>
        <p className="auth-subtitle">A guided civic workflow — tell us what happened, where, and how private it should stay.</p>

        <Alert type="error">{formError}</Alert>
        <Alert type="error">{categoriesError}</Alert>

        <form onSubmit={handleSubmit} noValidate>
          <div className="form-step">
            <div className="form-step-head">
              <span className="form-step-number">1</span>
              <h2><MessageSquareText size={16} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />The Problem</h2>
            </div>
            <FormField
              label="Complaint Title"
              name="title"
              value={form.title}
              onChange={handleChange}
              error={fieldErrors.title}
              placeholder="Large pothole on Main Street"
            />
            <div className="form-field">
              <label htmlFor="description">Description</label>
              <textarea
                id="description"
                name="description"
                rows={5}
                value={form.description}
                onChange={handleChange}
                placeholder="Describe the issue in detail — what, where, and since when."
              />
              {fieldErrors.description && <span className="field-error">{fieldErrors.description}</span>}
            </div>
            <VoiceComplaintButton onTranscript={(text) => setForm((prev) => ({ ...prev, description: prev.description ? `${prev.description} ${text}` : text }))} />
          </div>

          <div className="form-step">
            <div className="form-step-head">
              <span className="form-step-number">2</span>
              <h2><Tag size={16} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Category</h2>
            </div>
            <div className="form-field">
              <label htmlFor="category_id">Category</label>
              <select id="category_id" name="category_id" value={form.category_id} onChange={handleChange}>
                <option value="">Select a category</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
              {fieldErrors.category_id && <span className="field-error">{fieldErrors.category_id}</span>}
            </div>
          </div>

          <div className="form-step">
            <div className="form-step-head">
              <span className="form-step-number">3</span>
              <h2><MapPin size={16} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Location</h2>
            </div>
            <p className="form-step-hint">All location fields are optional, but help route your complaint faster.</p>
            <FormField label="Address (optional)" name="address" value={form.address} onChange={handleChange} />
            <FormField label="City (optional)" name="city" value={form.city} onChange={handleChange} />
            <FormField label="District (optional)" name="district" value={form.district} onChange={handleChange} />
            <FormField label="Taluka (optional)" name="taluka" value={form.taluka} onChange={handleChange} />
            <FormField label="Village (optional)" name="village" value={form.village} onChange={handleChange} />
            <FormField label="State (optional)" name="state" value={form.state} onChange={handleChange} />
            <FormField
              label="Pincode (optional)"
              name="pincode"
              value={form.pincode}
              onChange={handleChange}
              error={fieldErrors.pincode}
              placeholder="400001"
            />
            <FormField
              label="Latitude (optional)"
              name="latitude"
              type="number"
              value={form.latitude}
              onChange={handleChange}
              error={fieldErrors.latitude}
              placeholder="19.0760"
            />
            <FormField
              label="Longitude (optional)"
              name="longitude"
              type="number"
              value={form.longitude}
              onChange={handleChange}
              error={fieldErrors.longitude}
              placeholder="72.8777"
            />
          </div>

          <div className="form-step">
            <div className="form-step-head">
              <span className="form-step-number">4</span>
              <h2><Paperclip size={16} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Evidence</h2>
            </div>
            <div className="form-field">
              <label htmlFor="files">Photos or documents (optional — JPG, PNG, or PDF, up to 10 MB each)</label>
              <input
                id="files"
                name="files"
                type="file"
                multiple
                accept=".jpg,.jpeg,.png,.pdf"
                onChange={handleFileChange}
              />
              {fieldErrors.files && <span className="field-error">{fieldErrors.files}</span>}
            </div>
          </div>

          <div className="form-step">
            <div className="form-step-head">
              <span className="form-step-number">5</span>
              <h2><Lock size={16} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Privacy</h2>
            </div>
            <p className="form-step-hint">Choose how much of your identity is visible while this complaint is processed.</p>
            <div className="form-field" style={{ marginBottom: 0 }}>
              <div className="privacy-options">
                {PRIVACY_OPTIONS.map((option) => (
                  <label key={option.value} className="privacy-option">
                    <input
                      type="radio"
                      name="privacy_mode"
                      value={option.value}
                      checked={form.privacy_mode === option.value}
                      onChange={handleChange}
                    />
                    <span>
                      <strong>{option.label}</strong>
                      <span className="privacy-option-description">{option.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div className="form-step">
            <div className="form-step-head">
              <span className="form-step-number">6</span>
              <h2><Eye size={16} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Review &amp; Submit</h2>
            </div>
            <p className="form-step-hint">We'll first check for existing government work on this issue, then submit your complaint.</p>
            <button type="submit" className="btn-primary" disabled={submitting}>
              {checkingExistingWork ? "Checking existing work..." : submitting ? "Submitting..." : "Review & Continue"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default NewGrievancePage;
