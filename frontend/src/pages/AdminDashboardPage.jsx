import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Landmark, ScrollText, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import { getAdminDashboard, getAdminPublicStatisticsGovernance } from "../services/api";

export default function AdminDashboardPage() {
  const { accessToken } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [governance, setGovernance] = useState(null);
  useEffect(() => { getAdminDashboard(accessToken).then(setData).catch(e => setError(e.message)); getAdminPublicStatisticsGovernance(accessToken).then(setGovernance).catch(() => null); }, [accessToken]);
  if (error) return <main className="page"><h1>Admin Dashboard</h1><div className="alert alert-error">{error}</div></main>;
  if (!data) return <main className="page"><h1>Admin Dashboard</h1><div className="loading-state"><span className="spinner" /> Loading governance overview...</div></main>;
  const cards = [
    ["Total grievances",data.total_grievances],["Submitted",data.submitted],["Under review",data.under_review],["Assigned",data.assigned],
    ["In progress",data.in_progress],["Resolved",data.resolved],["Closed",data.closed],["Rejected",data.rejected],
    ["Disputed",data.disputed],["Reopened",data.reopened],["High/Critical SLA risk",data.overdue_sla_risk],["Citizens",data.total_citizens],
    ["Officers",data.total_officers],["Active departments",data.active_departments],["Resolution rate",`${data.resolution_rate}%`],["Dispute rate",`${data.dispute_rate}%`]
  ];
  return <main className="page">
    <span className="badge neutral" style={{marginBottom:"0.6rem"}}><Landmark size={13} /> Government Command Center</span>
    <h1>Admin Dashboard</h1>
    <p>System-wide governance overview. Citizen identity is intentionally excluded from aggregate views.</p>
    <div className="dashboard-grid">{cards.map(([label,value])=><section className="card" key={label}><strong>{value}</strong><span>{label}</span></section>)}</div>
    {governance && <div className="card" style={{marginTop:24}}><h2><ShieldCheck size={17} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Public Civic Statistics Governance</h2><p>{governance.scores_manually_editable ? "Scores are manually editable." : "Individual civic scores are not manually editable."}</p><p>Ranking calculation: {governance.ranking_calculation_status}. Minimum sample: {governance.methodology.minimum_sample_size}.</p><div className="button-row"><Link to="/statistics">View public statistics</Link><Link to="/admin/audit"><ScrollText size={13} style={{verticalAlign:"-2px",marginRight:"0.3rem"}} />Review audit trail</Link></div></div>}
    <div className="card" style={{marginTop:16}}><h2>Management</h2><div className="button-row">
      <Link to="/admin/grievances">Grievances</Link><Link to="/admin/officers">Officers</Link><Link to="/admin/departments">Departments</Link><Link to="/admin/categories">Categories</Link>
      <Link to="/admin/privacy">Privacy</Link><Link to="/admin/audit">Audit</Link><Link to="/admin/ai">AI Governance</Link><Link to="/admin/analytics">Analytics</Link>
    </div></div>
  </main>;
}
