import { useEffect, useState } from 'react';
import { Settings, Mail, BellRing } from 'lucide-react';
import { getNotificationPreferences, updateNotificationPreferences, getNotificationConfig, subscribePush } from '../services/api';
import { useAuth } from '../context/AuthContext.jsx';
export default function NotificationPreferencesPage(){
 const {accessToken}=useAuth(); const [prefs,setPrefs]=useState({email_enabled:true,browser_enabled:false}); const [config,setConfig]=useState({}); const [message,setMessage]=useState('');
 useEffect(()=>{Promise.all([getNotificationPreferences(accessToken),getNotificationConfig(accessToken)]).then(([p,c])=>{setPrefs(p);setConfig(c)}).catch(e=>setMessage(e.message))},[accessToken]);
 const save=async key=>{const next={...prefs,[key]:!prefs[key]}; setPrefs(next); await updateNotificationPreferences(next,accessToken);};
 const enableBrowser=async()=>{setMessage(''); if(!('Notification' in window)||!('serviceWorker' in navigator)||!config.browser_push_available){setMessage('Browser push is not configured on the server.');return;} const permission=await Notification.requestPermission(); if(permission!=='granted'){setMessage('Browser notification permission was not granted.');return;} const reg=await navigator.serviceWorker.register('/sw.js'); const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:urlBase64ToUint8Array(config.vapid_public_key)}); await subscribePush(sub,accessToken); setPrefs({...prefs,browser_enabled:true}); setMessage('Browser notifications enabled.');};
 return <main className="page-shell">
   <div className="page-header"><h2><Settings size={19} style={{verticalAlign:"-3px",marginRight:"0.4rem"}} />Notification Preferences</h2></div>
   <div className="card">
     <div className="privacy-option" style={{cursor:"default"}}>
       <input type="checkbox" checked={prefs.email_enabled} onChange={()=>save('email_enabled')} id="pref-email" />
       <span><strong><Mail size={14} style={{verticalAlign:"-2px",marginRight:"0.35rem"}} />Email notifications</strong><span className="privacy-option-description">Receive updates about your grievances and followed projects by email.</span></span>
     </div>
     <div className="privacy-option" style={{cursor:"default", marginTop:"0.7rem"}}>
       <input type="checkbox" checked={prefs.browser_enabled} onChange={()=>prefs.browser_enabled ? save('browser_enabled') : enableBrowser()} id="pref-browser" />
       <span><strong><BellRing size={14} style={{verticalAlign:"-2px",marginRight:"0.35rem"}} />Browser notifications</strong><span className="privacy-option-description">Get a push notification in this browser when there's an update.</span></span>
     </div>
     {!prefs.browser_enabled&&config.browser_push_available&&<button className="btn-secondary" style={{marginTop:"1rem"}} onClick={enableBrowser}>Enable browser notifications</button>}
     {message&&<div className="alert alert-info" style={{marginTop:"1rem", marginBottom:0}}>{message}</div>}
     <small style={{display:"block", marginTop:"1rem"}}>SMS notifications are not available.</small>
   </div>
 </main>;
}
function urlBase64ToUint8Array(base64String){const padding='='.repeat((4-base64String.length%4)%4);const base64=(base64String+padding).replace(/-/g,'+').replace(/_/g,'/');const rawData=window.atob(base64);return Uint8Array.from([...rawData].map(c=>c.charCodeAt(0)));}
