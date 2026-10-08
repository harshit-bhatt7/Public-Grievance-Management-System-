import { useState } from "react";
import { Link } from "react-router-dom";
import { BrainCircuit, Sparkles } from "lucide-react";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { askCitizenAIAssistant } from "../services/api.js";

export default function CitizenAIAssistantPage() {
  const { accessToken } = useAuth();
  const [grievanceNumber, setGrievanceNumber] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  async function ask(e) {
    e.preventDefault(); setLoading(true); setError(null); setAnswer(null);
    try { setAnswer(await askCitizenAIAssistant(question, grievanceNumber, accessToken)); }
    catch (err) { setError(err.message || "Could not contact the AI assistant."); }
    finally { setLoading(false); }
  }
  return <div className="app-shell">
    <header className="app-header"><h1><BrainCircuit size={20} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Citizen AI Assistant</h1><p>AI-generated assistance — verify official information in your grievance record.</p></header>
    <div className="status-card" style={{maxWidth:700,width:"100%"}}>
      <Alert type="error">{error}</Alert>
      <form onSubmit={ask}>
        <div className="form-field"><label htmlFor="grievance-number">Grievance number (optional)</label><input id="grievance-number" value={grievanceNumber} onChange={e=>setGrievanceNumber(e.target.value)} placeholder="GRV-2026-000001" /></div>
        <div className="form-field"><label htmlFor="ai-question">Question</label><textarea id="ai-question" rows={4} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="What is the status of my complaint?" required /></div>
        <button className="btn-primary" disabled={loading}>{loading ? "Checking…" : "Ask assistant"}</button>
      </form>
      {answer && (
        <div className="match-card" style={{marginTop:"1.5rem"}}>
          <div className="match-card-head">
            <strong><Sparkles size={15} style={{verticalAlign:"-2px",marginRight:"0.35rem"}} />AI Assistant</strong>
            <span className="badge warning">AI-generated</span>
          </div>
          <p style={{marginBottom:"0.5rem"}}>{answer.answer || answer.message || "Information not available."}</p>
          <small>Provider: {answer.provider || "unknown"} · Confidence: {answer.confidence ?? "—"}</small>
        </div>
      )}
      <p className="footer-note"><Link to="/complaints">Back to my complaints</Link></p>
    </div>
  </div>;
}
