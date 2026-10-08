import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

const ICONS = {
  error: XCircle,
  success: CheckCircle2,
  warning: AlertTriangle,
  info: Info,
};

function Alert({ type = "error", children }) {
  if (!children) return null;
  const Icon = ICONS[type] || Info;
  return (
    <div className={`alert alert-${type}`} role={type === "error" ? "alert" : "status"}>
      <Icon size={18} style={{ flexShrink: 0, marginTop: "0.1rem" }} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

export default Alert;
