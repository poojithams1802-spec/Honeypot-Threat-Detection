import React from 'react';
import { AlertTriangle, Database } from 'lucide-react';

export function SystemBanners({ modelMode, hasDemoData }) {
  const isSynthetic = modelMode === 'synthetic';

  return (
    <div className="system-banners" data-testid="system-banners">
      {isSynthetic && (
        <div className="banner banner-amber" data-testid="synthetic-model-banner">
          <AlertTriangle size={18} />
          <span>
            <strong>DEMO MODEL</strong> - trained on synthetic data, predictions are not valid results
          </span>
        </div>
      )}
      {hasDemoData && (
        <div className="banner banner-info" data-testid="demo-data-banner">
          <Database size={18} />
          <span>
            <strong>Showing demo data</strong> - historical replay and synthesized sessions are active
          </span>
        </div>
      )}
    </div>
  );
}
