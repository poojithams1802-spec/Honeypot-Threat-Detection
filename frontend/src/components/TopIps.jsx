import React from 'react';

export function TopIps({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="glass-panel mini-card">
        <div className="card-header"><h3 className="card-title">Top Source IPs</h3></div>
        <div className="loader">No data</div>
      </div>
    );
  }

  return (
    <div className="glass-panel mini-card">
      <div className="card-header"><h3 className="card-title">Top Source IPs</h3></div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>IP Address</th>
              <th>Sessions</th>
              <th>Highest Threat</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            {data.map((ip, i) => (
              <tr key={i}>
                <td>{ip.src_ip}</td>
                <td>{ip.event_count}</td>
                <td>
                  <span className={`threat-badge threat-${ip.highest_threat_level?.toLowerCase() || 'low'}`}>
                    <span className="threat-dot" />
                    {ip.highest_threat_level}
                  </span>
                </td>
                <td>{ip.most_common_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
