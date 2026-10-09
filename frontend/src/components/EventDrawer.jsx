import React, { useEffect, useState } from 'react';
import { X, AlertCircle, Terminal, KeyRound, BarChart3, Database } from 'lucide-react';
import { api } from '../api/client';

export function EventDrawer({ event, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!event?.session_id) {
      setDetail(null);
      return;
    }

    setDetail(event);
    setLoading(true);
    api.getEvent(event.session_id).then((res) => {
      if (res.data) {
        setDetail(res.data);
      }
      setLoading(false);
    });
  }, [event]);

  if (!event) return null;

  const current = detail || event;
  const features = current.features || {};
  const probabilities = current.probabilities || {};

  // Build "Why this was flagged" strictly from real feature fields (no invented text)
  const flaggedReasons = [];
  if (features.n_suspicious_commands > 0) {
    flaggedReasons.push(`${features.n_suspicious_commands} suspicious command(s) executed`);
  }
  if (features.n_login_failed > 0) {
    flaggedReasons.push(`${features.n_login_failed} failed login attempt(s) recorded`);
  }
  if (features.n_download_attempts > 0) {
    flaggedReasons.push(`${features.n_download_attempts} file download attempt(s) detected`);
  }
  if (features.n_file_uploads > 0) {
    flaggedReasons.push(`${features.n_file_uploads} file upload attempt(s) detected`);
  }
  if (current.is_anomalous) {
    flaggedReasons.push(
      `Isolation Forest anomaly detector flagged session (anomaly score: ${current.anomaly_score?.toFixed(3)})`
    );
  }
  if (features.ip_sessions_last_300s > 1) {
    flaggedReasons.push(`${features.ip_sessions_last_300s} sessions initiated from this IP within 300s`);
  }
  if (features.ip_failed_logins_last_300s > 0) {
    flaggedReasons.push(`${features.ip_failed_logins_last_300s} failed login attempts from this IP within 300s`);
  }
  if (features.ip_distinct_usernames_last_300s > 1) {
    flaggedReasons.push(
      `Credential spraying pattern: ${features.ip_distinct_usernames_last_300s} distinct usernames tested within 300s`
    );
  }
  if (features.no_login_attempted === 1) {
    flaggedReasons.push('Direct connection without authentication attempt');
  }
  if (features.session_incomplete === 1) {
    flaggedReasons.push('Session terminated abnormally or timed out');
  }
  if (flaggedReasons.length === 0) {
    flaggedReasons.push(
      `Model classification: ${current.predicted_label} with ${(current.confidence * 100).toFixed(1)}% confidence`
    );
  }

  const commandsList = current.commands || [];
  const usernamesList = current.usernames || [];
  const passwordsList = current.passwords || [];

  return (
    <>
      <div className={`drawer-overlay ${event ? 'open' : ''}`} onClick={onClose} />
      <div className={`drawer ${event ? 'open' : ''}`} data-testid="event-detail-drawer">
        <div className="drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h3 className="card-title">Session Details</h3>
            {current.is_demo && <span className="badge demo">DEMO</span>}
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close drawer">
            <X size={20} />
          </button>
        </div>

        <div className="drawer-content">
          {/* Metadata Cards */}
          <div className="detail-meta-grid">
            <div className="detail-item">
              <span className="detail-label">Session ID</span>
              <span className="detail-value mono">{current.session_id}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Source IP</span>
              <span className="detail-value mono">{current.src_ip}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Threat Level</span>
              <span className="detail-value">
                <span className={`threat-badge threat-${(current.threat_level || 'low').toLowerCase()}`}>
                  <span className="threat-dot" />
                  {current.threat_level || 'Unknown'}
                </span>
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Predicted Label</span>
              <span className="detail-value font-medium">{current.predicted_label || 'N/A'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Model Confidence</span>
              <span className="detail-value">
                {current.confidence != null ? `${(current.confidence * 100).toFixed(1)}%` : 'N/A'}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Duration</span>
              <span className="detail-value">
                {current.duration_sec != null ? `${current.duration_sec.toFixed(1)}s` : 'N/A'}
              </span>
            </div>
          </div>

          {/* Why this was flagged */}
          <div className="drawer-section" data-testid="flagged-reasons-section">
            <div className="section-title">
              <AlertCircle size={16} className="text-warning" />
              <span>Why This Was Flagged</span>
            </div>
            <ul className="flagged-list">
              {flaggedReasons.map((reason, idx) => (
                <li key={idx} className="flagged-item">
                  {reason}
                </li>
              ))}
            </ul>
          </div>

          {/* Class Probability Bar Chart */}
          <div className="drawer-section" data-testid="probabilities-section">
            <div className="section-title">
              <BarChart3 size={16} />
              <span>Class Probabilities</span>
            </div>
            <div className="prob-bars">
              {Object.keys(probabilities).length === 0 ? (
                <span className="empty-text">No probability breakdown available.</span>
              ) : (
                Object.entries(probabilities).map(([cls, prob]) => {
                  const pct = Math.round((prob || 0) * 100);
                  return (
                    <div key={cls} className="prob-row">
                      <div className="prob-label">
                        <span>{cls.replace('_', ' ')}</span>
                        <span className="mono">{pct}%</span>
                      </div>
                      <div className="prob-track">
                        <div
                          className={`prob-fill prob-fill-${cls.replace('_', '-')}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Commands Tried */}
          <div className="drawer-section" data-testid="commands-section">
            <div className="section-title">
              <Terminal size={16} />
              <span>Commands Executed ({commandsList.length})</span>
            </div>
            {commandsList.length === 0 ? (
              <span className="empty-text">None recorded</span>
            ) : (
              <div className="commands-list">
                {commandsList.map((cmd, i) => (
                  <div key={i} className="command-item mono">
                    $ {cmd}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Credentials Tried */}
          <div className="drawer-section" data-testid="credentials-section">
            <div className="section-title">
              <KeyRound size={16} />
              <span>Credentials Attempted</span>
            </div>
            <div className="creds-summary">
              <div>
                <span className="cred-sub-label">Usernames:</span>{' '}
                {usernamesList.length === 0 ? (
                  <span className="empty-text">None recorded</span>
                ) : (
                  usernamesList.map((u, i) => (
                    <span key={i} className="badge badge-subtle mono">
                      {u}
                    </span>
                  ))
                )}
              </div>
              <div style={{ marginTop: '0.5rem' }}>
                <span className="cred-sub-label">Passwords:</span>{' '}
                {passwordsList.length === 0 ? (
                  <span className="empty-text">None recorded</span>
                ) : (
                  passwordsList.map((p, i) => (
                    <span key={i} className="badge badge-subtle mono">
                      {p}
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Raw Features Expander */}
          <details className="drawer-section raw-features">
            <summary className="section-title" style={{ cursor: 'pointer' }}>
              <Database size={16} />
              <span>Raw Feature Vector ({Object.keys(features).length} fields)</span>
            </summary>
            <pre className="features-json mono">{JSON.stringify(features, null, 2)}</pre>
          </details>
        </div>
      </div>
    </>
  );
}
