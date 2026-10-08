import { useEffect,useState } from 'react';import {Link} from 'react-router-dom';import {FolderKanban, PlusCircle, ArrowRight} from 'lucide-react';import {getAdminProjects} from '../services/api';import {useAuth} from '../context/AuthContext';

function ProjectStatusBadge({ state }) {
  const className = `badge status-${(state || '').toLowerCase()}`;
  return <span className={className}>{(state || '').replace(/_/g, ' ')}</span>;
}

export default function AdminProjectsPage(){const{accessToken}=useAuth();const[p,setP]=useState(null);useEffect(()=>{getAdminProjects(accessToken).then(setP)},[accessToken]);return <main className="stats-page"><section className="stats-hero"><div><span className="eyebrow"><FolderKanban size={13} style={{verticalAlign:"-2px",marginRight:"0.3rem"}} />ADMIN GOVERNANCE</span><h1>Government Projects</h1><p>Create, update and audit transparent public projects.</p></div><Link className="btn-primary" to="/admin/projects/new"><PlusCircle size={16} /> New Project</Link></section>
{!p ? <div className="loading-state"><span className="spinner" /> Loading projects...</div> : p.length===0 ? <div className="empty-state"><FolderKanban size={28} className="empty-state-icon" /><h3>No projects yet</h3><p>Create the first government project to start tracking public work.</p></div> : <section className="stats-grid">{p.map(x=><article className="panel" key={x.id}><div className="panel-head"><div><span className="eyebrow">{x.project_number}</span><h2>{x.name}</h2></div><ProjectStatusBadge state={x.status} /></div><div className="progress"><i style={{width:`${x.progress_percent}%`}}/></div><p className="muted">{x.progress_percent}% complete</p><Link className="btn-link" to={`/admin/projects/${x.id}`}>Manage <ArrowRight size={14} /></Link></article>)}</section>}
</main>}
