import React, { useState } from 'react';
import { Search, ChevronLeft, ChevronRight, Filter } from 'lucide-react';

export function EventsTable({
  events = [],
  onSelectEvent,
  threatFilter = '',
  onThreatFilterChange,
  searchFilter = '',
  onSearchFilterChange,
  anomalyFilter = false,
  onAnomalyFilterChange,
  page = 1,
  onPageChange,
  pageSize = 15,
}) {
  // Filter events client-side based on the current props
  const filtered = events.filter((ev) => {
    if (threatFilter && ev.threat_level?.toLowerCase() !== threatFilter.toLowerCase()) {
      return false;
    }
    if (anomalyFilter && !ev.is_anomalous) {
      return false;
    }
    if (searchFilter) {
      const q = searchFilter.toLowerCase();
      const ip = (ev.src_ip || '').toLowerCase();
      const sid = (ev.session_id || '').toLowerCase();
      const label = (ev.predicted_label || '').toLowerCase();
      if (!ip.includes(q) && !sid.includes(q) && !label.includes(q)) {
        return false;
      }
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const startIdx = (currentPage - 1) * pageSize;
  const pageItems = filtered.slice(startIdx, startIdx + pageSize);

  return (
    <div className="glass-panel table-card" data-testid="events-table-card">
      <div className="card-header" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h3 className="card-title">Recent Activity</h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Showing {filtered.length} of {events.length} sessions
          </span>
        </div>

        {/* Filter Controls */}
        <div className="table-controls">
          <div className="search-box">
            <Search size={14} />
            <input
              type="text"
              placeholder="Search IP, session, label..."
              value={searchFilter}
              onChange={(e) => {
                onSearchFilterChange(e.target.value);
                onPageChange(1);
              }}
              data-testid="events-search-input"
            />
          </div>

          <div className="filter-select">
            <Filter size={14} />
            <select
              value={threatFilter}
              onChange={(e) => {
                onThreatFilterChange(e.target.value);
                onPageChange(1);
              }}
              data-testid="events-threat-select"
            >
              <option value="">All Threats</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>

          <label className="checkbox-toggle">
            <input
              type="checkbox"
              checked={anomalyFilter}
              onChange={(e) => {
                onAnomalyFilterChange(e.target.checked);
                onPageChange(1);
              }}
              data-testid="events-anomaly-toggle"
            />
            <span>Anomalous only</span>
          </label>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" data-testid="events-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Session</th>
              <th>Source IP</th>
              <th>Threat</th>
              <th>Label</th>
              <th>Confidence</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((ev, i) => (
              <tr
                key={ev.session_id || i}
                onClick={() => onSelectEvent && onSelectEvent(ev)}
                data-testid={`event-row-${ev.session_id}`}
                style={{ cursor: 'pointer' }}
              >
                <td>{new Date((ev.start_time || 0) * 1000).toLocaleTimeString()}</td>
                <td className="mono">{ev.session_id}</td>
                <td className="mono">{ev.src_ip}</td>
                <td>
                  <span className={`threat-badge threat-${(ev.threat_level || 'low').toLowerCase()}`}>
                    <span className="threat-dot" />
                    {ev.threat_level || 'Unknown'}
                  </span>
                </td>
                <td>{ev.predicted_label || '-'}</td>
                <td>
                  {ev.confidence != null ? `${(ev.confidence * 100).toFixed(0)}%` : '-'}
                </td>
                <td>{ev.duration_sec != null ? `${ev.duration_sec.toFixed(1)}s` : '-'}</td>
                <td>
                  <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                    {ev.is_demo && (
                      <span className="badge demo" data-testid="demo-badge">
                        DEMO
                      </span>
                    )}
                    {ev.is_anomalous && (
                      <span className="badge badge-warning">ANOMALY</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {pageItems.length === 0 && (
              <tr>
                <td
                  colSpan="8"
                  style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}
                >
                  No matching sessions found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="table-pagination" data-testid="table-pagination">
          <button
            className="btn btn-sm"
            disabled={currentPage <= 1}
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            data-testid="pagination-prev"
          >
            <ChevronLeft size={14} /> Prev
          </button>
          <span className="page-indicator">
            Page {currentPage} of {totalPages}
          </span>
          <button
            className="btn btn-sm"
            disabled={currentPage >= totalPages}
            onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
            data-testid="pagination-next"
          >
            Next <ChevronRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
