import { Fragment, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Building2, ClipboardList, ArrowRight, Megaphone, CheckCircle2, SearchX } from 'lucide-react';
import { getPublicProjectCategories, getPublicProjectDepartments, getPublicProjects, getPublicProjectStatistics } from '../services/api';

const FLOW_STEPS = [
  { icon: Building2, label: 'Government Project' },
  { icon: ClipboardList, label: 'Related Civic Issues' },
  { icon: Megaphone, label: 'Citizen Grievances' },
  { icon: ArrowRight, label: 'Government Response' },
  { icon: CheckCircle2, label: 'Resolution' },
];

function ProjectStatusBadge({ state }) {
  const className = `badge status-${(state || '').toLowerCase()}`;
  return <span className={className}>{(state || '').replace(/_/g, ' ')}</span>;
}

export default function PublicProjectsPage(){
 const [projects,setProjects]=useState([]),[stats,setStats]=useState(null),[cats,setCats]=useState([]),[deps,setDeps]=useState([]),[filters,setFilters]=useState({}),[loading,setLoading]=useState(true);
 useEffect(()=>{setLoading(true);Promise.all([getPublicProjects(filters),getPublicProjectStatistics(),getPublicProjectCategories(),getPublicProjectDepartments()]).then(([p,s,c,d])=>{setProjects(p);setStats(s);setCats(c.items||[]);setDeps(d.items||[])}).catch(()=>{}).finally(()=>setLoading(false))},[filters]);
 const set=(k,v)=>setFilters(x=>({...x,[k]:v}));
 return <main className="stats-page"><section className="stats-hero"><div><span className="eyebrow">GOVERNMENT PROJECT TRANSPARENCY</span><h1>Track public projects</h1><p>Discover government work, progress, timelines, evidence and public accountability.</p></div></section>

 <div className="section-title"><h2>How grievances drive government action</h2></div>
 <div className="flow-diagram">
   {FLOW_STEPS.map(({ icon: Icon, label }, i) => (
     <Fragment key={label}>
       <div className="flow-step">
         <span className="flow-step-icon"><Icon size={18} /></span>
         <strong>{label}</strong>
       </div>
       {i < FLOW_STEPS.length - 1 && <span className="flow-arrow"><ArrowRight size={18} /></span>}
     </Fragment>
   ))}
 </div>

 <section className="metric-grid">{stats&&[['Total projects',stats.total_projects],['Upcoming',stats.upcoming_projects],['Active',stats.active_projects],['Completed',stats.completed_projects],['Delayed',stats.delayed_projects]].map(x=><article key={x[0]}><span>{x[0]}</span><strong>{x[1]}</strong></article>)}</section>
 <section className="geo-bar"><label><span>Search</span><input placeholder="Project name or ID" value={filters.q||''} onChange={e=>set('q',e.target.value)}/></label><label><span>Category</span><select value={filters.category||''} onChange={e=>set('category',e.target.value)}><option value="">All</option>{cats.map(c=><option key={c}>{c}</option>)}</select></label><label><span>Department</span><select value={filters.department_id||''} onChange={e=>set('department_id',e.target.value)}><option value="">All</option>{deps.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label><label><span>Status</span><select value={filters.status||''} onChange={e=>set('status',e.target.value)}><option value="">All</option>{['UPCOMING','PLANNED','APPROVED','IN_PROGRESS','ON_HOLD','COMPLETED','DELAYED','CANCELLED'].map(x=><option key={x}>{x.replace(/_/g,' ')}</option>)}</select></label></section>

 {loading ? (
   <div className="loading-state"><span className="spinner" /> Loading government projects...</div>
 ) : (
   <section className="stats-grid">{projects.map(p=><article className="panel" key={p.id}><div className="panel-head"><div><span className="eyebrow">{p.project_number}</span><h2>{p.name}</h2></div><ProjectStatusBadge state={p.schedule_state} /></div><p>{p.description}</p><div className="list-row"><span>{p.category} · {p.department_name||'Department not listed'}</span><b>{p.progress_percent}%</b></div><div className="progress"><i style={{width:`${p.progress_percent}%`}}/></div><div className="list-row"><span>{[p.state,p.district,p.taluka,p.village].filter(Boolean).join(' · ')||'Location not listed'}</span><small>{p.expected_completion_date||'No completion date'}</small></div><Link className="btn-link" to={`/projects/${p.id}`}>View project <ArrowRight size={14} /></Link></article>)}</section>
 )}
 {!loading && projects.length===0&&<div className="empty-state"><SearchX size={28} className="empty-state-icon" /><h3>No projects found</h3><p>Try clearing one or more filters.</p></div>}
 </main>
}
