import { Clock3, MessageSquareText, Workflow } from "lucide-react";

import type { RunEvent } from "../types";
import { eventTone, formatEventLabel, formatTime, statusBgTone } from "../utils";

export function TimelineStrip({
  events,
  onSelectNode,
}: {
  events: RunEvent[];
  onSelectNode: (id: string) => void;
}) {
  return (
    <section className="activity-panel">
      <div className="activity-header">
        <div>
          <span className="eyebrow">Activity</span>
          <h3>Recent history</h3>
        </div>
        <span className="quiet-meta">{events.length} events</span>
      </div>

      <div className="activity-list">
        {events.length ? (
          events.map((event, index) => {
            const tone = eventTone(event.event).replace("status-", "");
            return (
              <button
                key={`${event.timestamp}-${event.event}-${event.nodeId ?? "run"}-${index}`}
                type="button"
                className={`activity-card ${event.nodeId ? "interactive" : ""}`}
                onClick={() => {
                  if (event.nodeId) {
                    onSelectNode(event.nodeId);
                  }
                }}
              >
                <div className={`activity-marker ${statusBgTone(tone)}`} />
                <div className="activity-copy">
                  <div className="activity-copy-top">
                    <strong>{formatEventLabel(event.event)}</strong>
                    <span>
                      <Clock3 size={14} />
                      {formatTime(event.timestamp)}
                    </span>
                  </div>
                  <p>{event.message ?? "No additional message was recorded for this event."}</p>
                  <div className="activity-meta">
                    <span>
                      <Workflow size={13} />
                      {event.nodeId ?? "run-wide"}
                    </span>
                    <span>
                      <MessageSquareText size={13} />
                      {Object.keys(event.payload ?? {}).length} payload keys
                    </span>
                  </div>
                </div>
              </button>
            );
          })
        ) : (
          <div className="empty-state compact">
            <h3>No activity yet</h3>
            <p>Events will appear here as the workflow starts progressing.</p>
          </div>
        )}
      </div>
    </section>
  );
}
