import { useEffect,useState } from 'react';
import { useParams } from 'react-router-dom';
import { MapPin, Users, IndianRupee, Clock, Milestone, Megaphone } from 'lucide-react';
import { getPublicProject,followProject,unfollowProject } from '../services/api';
import { useAuth } from '../context/AuthContext';

function ProjectStatusBadge({ state }) {
  const className = `badge status-${(state || '').toLowerCase()}`;
  return <span className={className}>{(state || '').replace(/_/g, ' ')}</span>;
}

export default function ProjectDetailPage(){const {id}=useParams();const {user,accessToken}=useAuth();const [p,setP]=useState(null);useEffect(()=>{getPublicProject(id,accessToken).then(setP)},[id,accessToken]);
 if(!p)return <main className="stats-page"><div className="loading-state"><span className="spinner" /> Loading project...</div></main>;
 const follow=async()=>{const r=p.is_following?await unfollowProject(id,accessToken):await followProject(id,accessToken);setP({...p,is_following:r.following})};
 return <main className="stats-page"><section className="stats-hero"><div><span className="eyebrow">{p.project_number}</span><h1>{p.name}</h1><p>{p.description}</p></div>{user?.user_type==='citizen'&&<button className="btn-primary" onClick={follow}>{p.is_following?'Unfollow Project':'Follow Project'}</button>}</section>

 <section className="metric-grid">
   <article><span>Status</span><strong style={{fontSize:"1.1rem"}}><ProjectStatusBadge state={p.schedule_state} /></strong></article>
   <article><span>Progress</span><strong>{p.progress_percent}%</strong><div className="progress"><i style={{width:`${p.progress_percent}%`}}/></div></article>
   <article><span>Department</span><strong style={{fontSize:"1rem"}}>{p.department_name||'—'}</strong></article>
   <article><span>Expected completion</span><strong style={{fontSize:"1rem"}}>{p.expected_completion_date||'—'}</strong></article>
 </section>

 <section className="stats-grid">
   <article className="panel"><h2><MapPin size={17} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Location &amp; Responsibility</h2><p>{[p.state,p.district,p.taluka,p.village].filter(Boolean).join(' → ')||'Not listed'}</p><p><Users size={14} style={{verticalAlign:"-2px",marginRight:"0.35rem"}} />{p.responsible_team||'Responsible team not listed'}{p.project_manager_name&&<> · {p.project_manager_name}{p.project_manager_designation?` (${p.project_manager_designation})`:''}</>}</p></article>
   <article className="panel"><h2><IndianRupee size={17} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Financial Information</h2><div className="list-row"><span>Approved</span><b>{p.approved_cost??'—'}</b></div><div className="list-row"><span>Revised</span><b>{p.revised_cost??'—'}</b></div><div className="list-row"><span>Public expenditure</span><b>{p.amount_spent??'—'}</b></div><p className="muted" style={{marginTop:"0.6rem",marginBottom:0}}>Only existing public-safe financial figures are shown.</p></article>
 </section>

 <section className="panel"><h2><Clock size={17} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Timeline</h2>{p.timeline.map((x,i)=><div className="list-row" key={i}><span><b>{x.date}</b> · {x.title}</span><small>{x.status||x.description||''}</small></div>)}</section>

 <section className="panel"><h2><Milestone size={17} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Milestones</h2>{p.milestones.length===0?<p className="muted">No milestones recorded yet.</p>:p.milestones.map(m=><div className="list-row" key={m.id}><span>{m.title}</span><b>{m.completion_percent}% · {m.status}</b></div>)}</section>

 <section className="panel"><h2><Megaphone size={17} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Related Grievances</h2><div className="metric-grid">{Object.entries(p.grievance_summary).filter(([k])=>['total','resolved','ongoing','pending','disputed'].includes(k)).map(([k,v])=><article key={k}><span>{k}</span><strong>{v}</strong></article>)}</div><p className="muted">Only aggregate public-safe grievance information is shown. Citizen identities and protected grievance details are never exposed.</p></section>
 </main>}
