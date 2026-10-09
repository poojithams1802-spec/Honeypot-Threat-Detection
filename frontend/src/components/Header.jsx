import React from 'react';
import { Shield, Activity, Clock, Database } from 'lucide-react';

const TIME_RANGES = [
  { label: '1h', value: 1 },
  { label: '6h', value: 6 },
  { label: '24h', value: 24 },
  { label: '48h', value: 48 },
  { label: 'All', value: 0 },
];

export function Header({
  mode,
  isConnected,
  timeRange = 0,
  onTimeRangeChange,
  includeDemo = true,
  onIncludeDemoChange,
}) {
  return (
    <header className="header" data-testid="soc-header">
      <div className="header-title">
        <Shield size={24} className="text-accent" />
        <span>Honeypot SOC Dashboard</span>
      </div>

      <div className="header-controls">
        {/* Time-Range Selector */}
        <div className="time-range-group" data-testid="time-range-selector">
          <Clock size={14} className="control-icon" />
          <div className="pill-group">
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.label}
                className={`pill-btn ${timeRange === tr.value ? 'active' : ''}`}
                onClick={() => onTimeRangeChange && onTimeRangeChange(tr.value)}
                data-testid={`time-range-${tr.label.toLowerCase()}`}
              >
                {tr.label}
              </button>
            ))}
          </div>
        </div>

        {/* Include Demo Toggle */}
        <label className="demo-toggle" data-testid="demo-data-toggle">
          <Database size={14} className="control-icon" />
          <input
            type="checkbox"
            checked={includeDemo}
            onChange={(e) => onIncludeDemoChange && onIncludeDemoChange(e.target.checked)}
          />
          <span>Demo Data</span>
        </label>

        {/* Connection status */}
        <div className="connection-status" data-testid="connection-status">
          <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          <span>{isConnected ? 'LIVE' : 'DISCONNECTED'}</span>
        </div>

        {/* Mode pill */}
        {mode === 'synthetic' && (
          <div className="mode-banner demo" data-testid="header-synthetic-badge">
            <Activity size={16} /> DEMO / SYNTHETIC
          </div>
        )}
        {mode === 'real' && (
          <div className="mode-banner real" data-testid="header-real-badge">
            <Shield size={16} /> REAL TRAFFIC
          </div>
        )}
      </div>
    </header>
  );
}
