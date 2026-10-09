import React from 'react';
import { WifiOff, RotateCw } from 'lucide-react';

export function OfflineState({ onRetry, message = 'Unable to connect to the Honeypot ML API service.' }) {
  return (
    <div className="offline-screen" data-testid="offline-state">
      <div className="glass-panel offline-card">
        <WifiOff size={48} className="text-danger pulse-slow" />
        <h2>API Service Offline</h2>
        <p>{message}</p>
        <p className="offline-hint">
          Ensure the FastAPI backend is running on <code>http://localhost:8000</code>.
        </p>
        <button className="btn btn-primary" onClick={onRetry}>
          <RotateCw size={16} /> Retry Connection
        </button>
      </div>
    </div>
  );
}
