import React from 'react';

export function KpiCard({ title, value, icon, valueColorClass = '' }) {
  return (
    <div className="glass-panel kpi-card">
      <div className="kpi-title">{icon} {title}</div>
      <div className={`kpi-value ${valueColorClass}`}>{value}</div>
    </div>
  );
}
