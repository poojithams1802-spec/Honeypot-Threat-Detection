import React from 'react';
import { Gauge } from 'lucide-react';

export function SecurityGauge({ score, penalties }) {
  const radius = 70;
  const circumference = Math.PI * radius; // half circle
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const offset = circumference * (1 - pct);

  const color =
    score >= 80 ? '#10b981' :
    score >= 50 ? '#eab308' :
    '#ef4444';

  return (
    <div className="glass-panel donut-card" style={{ alignItems: 'center' }}>
      <div className="card-header" style={{ width: '100%' }}>
        <h3 className="card-title">Security Score</h3>
      </div>
      <div style={{ position: 'relative', width: 180, height: 110 }}>
        <svg viewBox="0 0 180 110" width="180" height="110">
          {/* Background arc */}
          <path
            d="M 10 100 A 70 70 0 0 1 170 100"
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth="12"
            strokeLinecap="round"
          />
          {/* Score arc */}
          <path
            d="M 10 100 A 70 70 0 0 1 170 100"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{
              filter: `drop-shadow(0 0 8px ${color})`,
              transition: 'stroke-dashoffset 1s ease-out, stroke 0.5s ease',
            }}
          />
        </svg>
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: '50%',
            transform: 'translateX(-50%)',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '2rem', fontWeight: 700, color, lineHeight: 1 }}>
            {score}
          </div>
          <div style={{ fontSize: '0.7rem', color: '#9ba1b0', marginTop: 2 }}>/ 100</div>
        </div>
      </div>
      {penalties && (
        <div style={{ width: '100%', marginTop: '0.5rem' }}>
          {Object.entries(penalties).map(([level, val]) =>
            val > 0 ? (
              <div key={level} className="penalty-row">
                <span className="penalty-label">{level}</span>
                <span className="penalty-value">-{val}</span>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}
