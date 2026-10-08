import { Check, Circle, X } from "lucide-react";

const NORMAL_FLOW = ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED"];

const STEP_LABELS = {
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under Review",
  ASSIGNED: "Assigned",
  IN_PROGRESS: "In Progress",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
  REJECTED: "Rejected",
};

function formatTimestamp(isoString) {
  if (!isoString) return null;
  return new Date(isoString).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TimelineNode({ marker, label, state, timestamp, remarks }) {
  return (
    <div className={`timeline-node timeline-${state}`}>
      <div className="timeline-marker">{marker}</div>
      <div className="timeline-content">
        <div className="timeline-label">{label}</div>
        {timestamp && <div className="timeline-timestamp">{timestamp}</div>}
        {remarks && <div className="timeline-remarks">{remarks}</div>}
      </div>
    </div>
  );
}

/**
 * Renders a grievance's progress as a vertical timeline.
 *
 * - Normal flow (SUBMITTED → UNDER_REVIEW → ASSIGNED → IN_PROGRESS →
 *   RESOLVED → CLOSED): completed steps get a checkmark, the current
 *   status gets a filled marker, everything after it is shown as an
 *   empty/future step — never implying progress that hasn't happened.
 * - If the grievance was REJECTED, the timeline shows only the steps
 *   that actually occurred (from `history`) ending in an explicit
 *   "Rejected" node — it does not pretend the grievance is still
 *   progressing through the normal flow.
 */
function StatusTimeline({ currentStatus, history = [] }) {
  const historyByStatus = new Map(history.map((entry) => [entry.new_status, entry]));

  if (currentStatus === "REJECTED") {
    return (
      <div className="status-timeline">
        {history.map((entry, index) => {
          const isRejection = entry.new_status === "REJECTED";
          return (
            <TimelineNode
              key={`${entry.new_status}-${index}`}
              marker={isRejection ? <X size={14} /> : <Check size={14} />}
              label={STEP_LABELS[entry.new_status] || entry.new_status}
              state={isRejection ? "rejected" : "completed"}
              timestamp={formatTimestamp(entry.changed_at)}
              remarks={entry.remarks}
            />
          );
        })}
      </div>
    );
  }

  const currentIndex = NORMAL_FLOW.indexOf(currentStatus);

  return (
    <div className="status-timeline">
      {NORMAL_FLOW.map((step, index) => {
        const entry = historyByStatus.get(step);
        const state = index < currentIndex ? "completed" : index === currentIndex ? "current" : "future";
        const marker = state === "completed" ? <Check size={14} /> : state === "current" ? <Circle size={10} fill="currentColor" /> : <Circle size={10} />;

        return (
          <TimelineNode
            key={step}
            marker={marker}
            label={STEP_LABELS[step]}
            state={state}
            timestamp={entry ? formatTimestamp(entry.changed_at) : null}
            remarks={entry ? entry.remarks : null}
          />
        );
      })}
    </div>
  );
}

export default StatusTimeline;
