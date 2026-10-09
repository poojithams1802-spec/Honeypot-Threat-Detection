import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export function ThreatChart({ data }) {
  const chartData = [
    { name: 'Low', count: data?.Low || 0, fill: '#3b82f6' },
    { name: 'Medium', count: data?.Medium || 0, fill: '#eab308' },
    { name: 'High', count: data?.High || 0, fill: '#f97316' },
    { name: 'Critical', count: data?.Critical || 0, fill: '#ef4444' }
  ];

  return (
    <div className="glass-panel chart-card">
      <div className="card-header">
        <h3 className="card-title">Events by Threat Level</h3>
      </div>
      <div style={{ height: '300px' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
            <XAxis dataKey="name" stroke="#9ba1b0" tick={{ fill: '#9ba1b0' }} />
            <YAxis stroke="#9ba1b0" tick={{ fill: '#9ba1b0' }} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#14141e', borderColor: 'rgba(255,255,255,0.1)', borderRadius: '8px' }}
              itemStyle={{ color: '#f0f0f5' }}
              cursor={{ fill: 'rgba(255,255,255,0.05)' }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
