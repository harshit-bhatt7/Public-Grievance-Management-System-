import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { Database, Inbox } from "lucide-react";
import { useAuth } from "../context/AuthContext.jsx";
import * as api from "../services/api";

function JsonTable({ data }) {
  if (!Array.isArray(data)) return <pre>{JSON.stringify(data, null, 2)}</pre>;
  if (!data.length) return <div className="empty-state"><Inbox size={26} className="empty-state-icon" /><p style={{margin:0}}>No records.</p></div>;
  const keys = Object.keys(data[0]);
  return <div style={{overflowX:"auto"}}><table><thead><tr>{keys.map(k=><th key={k}>{k.replaceAll("_"," ")}</th>)}</tr></thead><tbody>{data.map((row,i)=><tr key={i}>{keys.map(k=><td key={k}>{typeof row[k]==="object"?JSON.stringify(row[k]):String(row[k] ?? "")}</td>)}</tr>)}</tbody></table></div>;
}

export default function AdminManagementPage() {
  const { accessToken } = useAuth();
  const { pathname } = useLocation();
  const [data,setData]=useState(null); const [error,setError]=useState(""); const [message,setMessage]=useState("");
  const load=()=>{
    const fn=pathname.includes("/grievances")?api.getAdminGrievances:pathname.includes("/officers")?api.getAdminOfficers:pathname.includes("/departments")?api.getAdminDepartments:pathname.includes("/categories")?api.getAdminCategories:pathname.includes("/privacy")?api.getAdminPrivacyRequests:pathname.includes("/audit")?api.getAdminAudit:pathname.includes("/ai")?api.getAdminAI:api.getAdminAnalytics;
    fn(accessToken).then(setData).catch(e=>setError(e.message));
  };
  useEffect(()=>{setError("");load()},[pathname,accessToken]);
  const action=async(fn)=>{setMessage("");setError("");try{await fn();setMessage("Saved successfully.");load()}catch(e){setError(e.message)}};
  if(error && !data)return <main className="page"><h1>Admin</h1><div className="alert alert-error">{error}</div></main>;
  if(!data)return <main className="page"><h1>Admin</h1><div className="loading-state"><span className="spinner" /> Loading records...</div></main>;
  const title=pathname.split("/").pop().replaceAll("-"," ");
  return <main className="page">
    <span className="badge neutral" style={{marginBottom:"0.6rem"}}><Database size={13} /> Admin Records</span>
    <h1>{title.toUpperCase()}</h1>
    {message&&<div className="alert alert-success">{message}</div>}
    {error&&<div className="alert alert-error">{error}</div>}
    {pathname.endsWith("/officers") && <OfficerForm accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/departments") && <DepartmentForm accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/categories") && <CategoryForm accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/privacy") && <PrivacyActions data={data} accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/audit") && <AuditActions accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/officers") && <OfficerActions data={data} accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/departments") && <DepartmentActions data={data} accessToken={accessToken} onDone={load} onError={setError}/>}
    {pathname.endsWith("/categories") && <CategoryActions data={data} accessToken={accessToken} onDone={load} onError={setError}/>}
    <div className="card" style={{marginTop:16}}><h2 style={{marginBottom:"0.75rem"}}>Records</h2><JsonTable data={data}/></div>
  </main>;
}

function OfficerForm({accessToken,onDone,onError}){const [f,setF]=useState({name:"",email:"",password:"",employee_id:"",department_id:"",designation:""});const [deps,setDeps]=useState([]);useEffect(()=>{api.getAdminDepartments(accessToken).then(setDeps).catch(e=>onError(e.message))},[accessToken]);return <form className="card" onSubmit={e=>{e.preventDefault();api.createAdminOfficer(f,accessToken).then(onDone).catch(e=>onError(e.message))}}><h2>Create officer</h2>{["name","email","password","employee_id","designation","department_id"].map(k=><input key={k} required={k!=="designation"} type={k==="password"?"password":"text"} placeholder={k.replaceAll("_"," ")} value={f[k]} onChange={e=>setF({...f,[k]:e.target.value})}/>)}<select value={f.department_id} onChange={e=>setF({...f,department_id:e.target.value})}><option value="">Select department</option>{deps.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select><button type="submit" className="btn-primary">Create officer</button></form>}
function DepartmentForm({accessToken,onDone,onError}){const [f,setF]=useState({name:"",description:"",contact_email:"",contact_phone:""});return <form className="card" onSubmit={e=>{e.preventDefault();api.createAdminDepartment(f,accessToken).then(onDone).catch(e=>onError(e.message))}}><h2>Create department</h2>{Object.keys(f).map(k=><input key={k} placeholder={k.replaceAll("_"," ")} value={f[k]} onChange={e=>setF({...f,[k]:e.target.value})}/>)}<button type="submit" className="btn-primary">Create department</button></form>}
function CategoryForm({accessToken,onDone,onError}){const [f,setF]=useState({name:"",description:"",department_id:""});const [deps,setDeps]=useState([]);useEffect(()=>{api.getAdminDepartments(accessToken).then(setDeps).catch(e=>onError(e.message))},[accessToken]);return <form className="card" onSubmit={e=>{e.preventDefault();api.createAdminCategory({...f,department_id:f.department_id||null},accessToken).then(onDone).catch(e=>onError(e.message))}}><h2>Create category</h2><input placeholder="name" value={f.name} onChange={e=>setF({...f,name:e.target.value})}/><input placeholder="description" value={f.description} onChange={e=>setF({...f,description:e.target.value})}/><select value={f.department_id} onChange={e=>setF({...f,department_id:e.target.value})}><option value="">No mapping</option>{deps.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select><button type="submit" className="btn-primary">Create category</button></form>}
function PrivacyActions({data,accessToken,onDone,onError}){const pending=data.filter(r=>r.status==="PENDING");return <div className="card"><h2>Pending privacy governance</h2>{pending.length===0?<p className="muted">No pending privacy requests.</p>:pending.map(r=><div key={r.id} className="status-row" style={{flexDirection:"column",alignItems:"stretch"}}><strong>{r.grievance_number}</strong><p style={{margin:"0.3rem 0 0.6rem"}}>{r.reason}</p><div className="button-row" style={{marginTop:0}}><button className="btn-primary" onClick={()=>api.approveAdminPrivacyRequest(r.id,"Approved by admin",accessToken).then(onDone).catch(e=>onError(e.message))}>Approve</button><button className="btn-danger" onClick={()=>api.rejectAdminPrivacyRequest(r.id,"Rejected by admin",accessToken).then(onDone).catch(e=>onError(e.message))}>Reject</button></div></div>)}</div>}
function AuditActions({accessToken,onDone,onError}){const [result,setResult]=useState(null);return <div className="card"><h2>Audit integrity check</h2><button className="btn-secondary" onClick={()=>api.verifyAdminAudit(accessToken).then(setResult).catch(e=>onError(e.message))}>Verify audit integrity</button>{result&&<pre>{JSON.stringify(result,null,2)}</pre>}</div>}

function OfficerActions({data,accessToken,onDone,onError}){return <div className="card"><h2>Officer controls</h2>{data.map(o=><div key={o.user_id} className="status-row"><span><strong>{o.name}</strong> — {o.employee_id} — {o.department_name||"Unassigned"}</span>{o.is_active&&<button className="btn-danger" onClick={()=>api.deactivateAdminOfficer(o.user_id,accessToken).then(onDone).catch(e=>onError(e.message))}>Deactivate</button>}</div>)}</div>}
function DepartmentActions({data,accessToken,onDone,onError}){return <div className="card"><h2>Department controls</h2>{data.map(d=><div key={d.id} className="status-row"><strong>{d.name}</strong>{d.is_active&&<button className="btn-danger" onClick={()=>api.deactivateAdminDepartment(d.id,accessToken).then(onDone).catch(e=>onError(e.message))}>Deactivate</button>}</div>)}</div>}
function CategoryActions({data,accessToken,onDone,onError}){return <div className="card"><h2>Category controls</h2>{data.map(c=><div key={c.id} className="status-row"><strong>{c.name}</strong>{c.is_active&&<button className="btn-danger" onClick={()=>api.deactivateAdminCategory(c.id,accessToken).then(onDone).catch(e=>onError(e.message))}>Deactivate</button>}</div>)}</div>}
