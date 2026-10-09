import React from 'react';
import { AlertTriangle, ShieldAlert, ChevronRight } from 'lucide-react';

export function AlertsPanel({ alerts = [], onSelectAlert }) {
  const highCritical = alerts.filter(
    (a) => a.threat_level === 'High' || a.threat_level === 'Critical'
  );

  return (
    <div className="glass-panel alerts-card" data-testid="alerts-panel">
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ShieldAlert className="text-danger" size={20} />
          <h3 className="card-title">Priority Threat Alerts</h3>
        </div>
        <span className="badge badge-danger">
          {highCritical.length} High/Critical
        </span>
      </div>

      <div className="alerts-list">
        {highCritical.length === 0 ? (
          <div className="alerts-empty">No active High or Critical alerts.</div>
        ) : (
          highCritical.slice(0, 5).map((alert) => (
            <div
              key={alert.session_id || alert.id}
              className={`alert-item alert-${alert.threat_level.toLowerCase()}`}
              onClick={() => onSelectAlert && onSelectAlert(alert)}
              data-testid={`alert-item-${alert.session_id}`}
            >
              <div className="alert-meta">
                <span className={`threat-badge threat-${alert.threat_level.toLowerCase()}`}>
                  {alert.threat_level}
                </span>
                <span className="alert-label">{alert.predicted_label}</span>
                <span className="alert-ip">{alert.src_ip}</span>
              </div>
              <div className="alert-action">
                <span className="alert-time">
                  {new Date((alert.start_time || 0) * 1000).toLocaleTimeString()}
                </span>
                <ChevronRight size={16} />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
