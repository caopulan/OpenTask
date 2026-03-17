import { Clock, MessageSquare, TerminalSquare } from "lucide-react";
import type { RunEvent } from "../types";
import { formatTime, eventTone } from "../utils";

export function TimelineStrip({
  events,
  onSelectNode,
}: {
  events: RunEvent[];
  onSelectNode: (id: string) => void;
}) {
  return (
    <section className="glass-panel flex-col" style={{ padding: "20px" }}>
      <div className="flex-row items-center justify-between mb-4 pb-4" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <div>
          <span className="kicker">Audit Trail</span>
          <h3 style={{ fontSize: "1.1rem" }}>Event Sequence</h3>
        </div>
        <div className="flex-row items-center gap-2">
          <TerminalSquare className="text-muted" size={18} />
          <span className="mono text-xs text-muted">{events.length} events logged</span>
        </div>
      </div>

      <div className="list-container" style={{ maxHeight: "300px" }}>
        {events.length ? (
          events.map((event, i) => (
            <button
              key={`${event.timestamp}-${event.event}-${event.nodeId ?? "run"}-${i}`}
              className={`card flex-row ${event.nodeId ? "hover" : ""} items-start gap-4`}
              style={{ padding: "12px 16px", cursor: event.nodeId ? "pointer" : "default", textAlign: "left" }}
              onClick={() => {
                if (event.nodeId) {
                  onSelectNode(event.nodeId);
                }
              }}
            >
              <div style={{ marginTop: "4px" }}>
                <div
                  className={`status-pill ${eventTone(event.event).replace('status-', 'bg-')}`}
                  style={{ width: "10px", height: "10px", padding: 0, border: `2px solid var(--${eventTone(event.event)})` }}
                />
              </div>

              <div className="flex-col gap-1 flex-1">
                <div className="flex-row justify-between items-center">
                  <strong style={{ fontSize: "0.95rem" }}>{event.event}</strong>
                  <span className="mono text-xs text-muted flex-row items-center gap-1">
                    <Clock size={12} />
                    {formatTime(event.timestamp)}
                  </span>
                </div>
                
                <p className="text-sm text-secondary mt-1">
                  {event.message ?? "No operation message recorded."}
                </p>

                <div className="flex-row gap-4 mt-2 mono text-xs text-muted">
                  <span className="flex-row items-center gap-1">
                    <TerminalSquare size={12} /> {event.nodeId ?? "run-wide scope"}
                  </span>
                  <span className="flex-row items-center gap-1">
                    <MessageSquare size={12} /> {Object.keys(event.payload ?? {}).length} payload keys
                  </span>
                </div>
              </div>
            </button>
          ))
        ) : (
          <div className="p-4 text-center text-muted text-sm">
            No events indexed for the selected run yet.
          </div>
        )}
      </div>
    </section>
  );
}
