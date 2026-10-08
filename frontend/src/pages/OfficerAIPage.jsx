import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, BrainCircuit, Sparkles } from "lucide-react";
import Alert from "../components/Alert.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getAICopilot, getAIDuplicates, getAIPriority, getAICategorySuggestion, getAIResponseDraft, getAIResolutionAnalysis, getAISLARisk, reviewAIRecommendation } from "../services/api.js";

export default function OfficerAIPage() {
  const { grievanceNumber } = useParams(); const { accessToken } = useAuth();
  const [result,setResult]=useState(null); const [error,setError]=useState(null); const [loading,setLoading]=useState(false);
  async function run(fn){setLoading(true);setError(null);try{setResult(await fn(grievanceNumber,accessToken));}catch(e){setError(e.message||"AI request failed.");}finally{setLoading(false);}}
  async function review(state){if(!result?.recommendation_id)return;try{setResult(await reviewAIRecommendation(result.recommendation_id,state,"Officer review",accessToken));}catch(e){setError(e.message||"Review failed.");}}
  return <div className="app-shell"><header className="app-header" style={{textAlign:"left"}}><p><Link to={`/officer/grievances/${encodeURIComponent(grievanceNumber)}`}><ArrowLeft size={13} style={{verticalAlign:"-2px",marginRight:"0.3rem"}} />Grievance</Link></p><h1><BrainCircuit size={20} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />AI Intelligence</h1><p className="case-id">{grievanceNumber}</p><Alert type="info">AI suggestions are advisory only — every recommendation requires human officer review before it takes effect.</Alert></header>
    <div className="status-card" style={{maxWidth:760,width:"100%"}}><Alert type="error">{error}</Alert>
      <h2 className="section-heading"><Sparkles size={16} />Run an AI analysis</h2>
      <div style={{display:"flex",gap:"0.6rem",flexWrap:"wrap"}}>{[["Category",getAICategorySuggestion],["Priority",getAIPriority],["Copilot",getAICopilot],["Duplicates",getAIDuplicates],["Response draft",getAIResponseDraft],["SLA risk",getAISLARisk]].map(([label,fn])=><button key={label} className="btn-secondary" disabled={loading} onClick={()=>run(fn)}>{loading?"Working…":label}</button>)}</div>
      <button className="btn-link" disabled={loading} style={{marginTop:"0.85rem"}} onClick={()=>run((n,t)=>getAIResolutionAnalysis(n,[],t))}>Analyze resolution evidence metadata</button>
      {result && <div style={{marginTop:"1.5rem",borderTop:"1px solid var(--color-border)",paddingTop:"1.25rem"}}><span className="badge warning" style={{marginBottom:"0.75rem"}}>AI-generated — Human Review Required</span><pre>{JSON.stringify(result,null,2)}</pre>{result.recommendation_id && <div className="button-row"><button className="btn-primary" onClick={()=>review("ACCEPTED")}>Accept recommendation</button><button className="btn-outline" onClick={()=>review("REJECTED")}>Reject</button><button className="btn-outline" onClick={()=>review("OVERRIDDEN")}>Override</button></div>}</div>}
    </div></div>;
}
