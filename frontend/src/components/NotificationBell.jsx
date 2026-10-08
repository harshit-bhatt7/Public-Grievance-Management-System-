import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { getUnreadNotificationCount } from '../services/api';
import { useAuth } from '../context/AuthContext.jsx';

export default function NotificationBell() {
  const { isAuthenticated, accessToken } = useAuth();
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!isAuthenticated || !accessToken) return;
    let active = true;
    const load = () => getUnreadNotificationCount(accessToken).then(x => { if (active) setCount(x.count || 0); }).catch(() => {});
    load(); const id = setInterval(load, 30000);
    return () => { active = false; clearInterval(id); };
  }, [isAuthenticated, accessToken]);
  if (!isAuthenticated) return null;
  return (
    <Link to="/notifications" className="notification-bell" aria-label={`Notifications${count > 0 ? `, ${count} unread` : ""}`}>
      <Bell size={18} />
      {count > 0 && <span className="notification-count">{count > 99 ? '99+' : count}</span>}
    </Link>
  );
}
