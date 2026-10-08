import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, BellOff, CheckCheck, ExternalLink } from 'lucide-react';
import { getNotifications, markNotificationRead, markAllNotificationsRead } from '../services/api';
import { useAuth } from '../context/AuthContext.jsx';
export default function NotificationCenterPage() {
  const { accessToken } = useAuth(); const [items,setItems]=useState(null); const [error,setError]=useState('');
  const load=()=>getNotifications(accessToken).then(setItems).catch(e=>setError(e.message||'We could not load this information. Please try again.'));
  useEffect(()=>{load()},[accessToken]);
  const read=async id=>{await markNotificationRead(id,accessToken);load()};
  const readAll=async()=>{await markAllNotificationsRead(accessToken);load()};
  const unreadCount = (items||[]).filter(n=>!n.read_at).length;
  return <main className="page-shell">
    <div className="page-header">
      <h2><Bell size={19} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Notifications{unreadCount>0 && <span className="badge pending" style={{marginLeft:"0.6rem"}}>{unreadCount} unread</span>}</h2>
      <button className="btn-outline" onClick={readAll}><CheckCheck size={15} /> Mark all as read</button>
    </div>
    {error&&<div className="alert alert-error">{error}</div>}
    {items===null && !error && <div className="loading-state"><span className="spinner" /> Loading your notifications...</div>}
    {items && items.length===0 ? (
      <div className="empty-state"><BellOff size={28} className="empty-state-icon" /><h3>No notifications</h3><p>You're all caught up — new updates on your grievances and followed projects will appear here.</p></div>
    ) : items && (
      <div className="notification-list">
        {items.map(n=>(
          <article key={n.id} className={`notification-item ${n.read_at?'read':'unread'}`}>
            <div>
              <strong>{n.title}</strong>
              <p>{n.message}</p>
              <small>{new Date(n.created_at).toLocaleString()}</small>
            </div>
            <div>
              {!n.read_at&&<button onClick={()=>read(n.id)}>Mark read</button>}
              {n.link_path&&<Link to={n.link_path}><ExternalLink size={13} style={{verticalAlign:"-2px",marginRight:"0.25rem"}} />Open</Link>}
            </div>
          </article>
        ))}
      </div>
    )}
  </main>;
}
