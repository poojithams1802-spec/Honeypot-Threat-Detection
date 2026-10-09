import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';

const COLORS = {
  normal: '#10b981',
  recon: '#eab308',
  brute_force: '#f97316',
  command_attack: '#ef4444',
};

const LABELS = {
  normal: 'Normal',
  recon: 'Recon',
  brute_force: 'Brute Force',
  command_attack: 'Command Attack',
};

export function AttackDonut({ data }) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="glass-panel donut-card">
        <div className="card-header"><h3 className="card-title">Attack Types</h3></div>
        <div className="loader">No data</div>
      </div>
    );
  }

  const chartData = Object.entries(data)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({
      name: LABELS[k] || k,
      value: v,
      fill: COLORS[k] || '#6366f1',
    }));

  if (chartData.length === 0) {
    return (
      <div className="glass-panel donut-card">
        <div className="card-header"><h3 className="card-title">Attack Types</h3></div>
        <div className="loader">No attacks detected</div>
      </div>
    );
  }

  return (
    <div className="glass-panel donut-card">
      <div className="card-header"><h3 className="card-title">Attack Types</h3></div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={3}
              dataKey="value"
              stroke="none"
            >
              {chartData.map((entry, i) => (
                <Cell key={i} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: '#14141e',
                borderColor: 'rgba(255,255,255,0.1)',
                borderRadius: '8px',
                fontSize: '0.875rem',
              }}
              itemStyle={{ color: '#f0f0f5' }}
            />
            <Legend
              iconType="circle"
              wrapperStyle={{ fontSize: '0.75rem', color: '#9ba1b0' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
