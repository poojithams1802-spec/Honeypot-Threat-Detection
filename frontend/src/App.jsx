import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from './api/client';
import { Header } from './components/Header';
import { SystemBanners } from './components/SystemBanners';
import { KpiCard } from './components/KpiCard';
import { ThreatChart } from './components/ThreatChart';
import { AttackDonut } from './components/AttackDonut';
import { SecurityGauge } from './components/SecurityGauge';
import { TopIps } from './components/TopIps';
import { TopCredentials } from './components/TopCredentials';
import { AlertsPanel } from './components/AlertsPanel';
import { EventsTable } from './components/EventsTable';
import { EventDrawer } from './components/EventDrawer';
import { ErrorBoundary } from './components/ErrorBoundary';
import { OfflineState } from './components/OfflineState';
import { useSSE } from './hooks/useSSE';
import {
  ShieldAlert, Users, Target, ActivitySquare,
  AlertTriangle, Wifi,
} from 'lucide-react';

const POLL_INTERVAL = 15_000;
const MAX_LIVE_EVENTS = 200;

export function Dashboard() {
  // Read initial query params from URL
  const queryParams = useMemo(() => new URLSearchParams(window.location.search), []);

  const [includeDemo, setIncludeDemo] = useState(
    queryParams.get('demo') !== 'false'
  );
  // Default to 0 ("All") ONLY when demo data is shown; otherwise default to 24 ("24h")
  const [timeRange, setTimeRange] = useState(() => {
    const fromUrl = queryParams.get('hours');
    if (fromUrl !== null) return Number(fromUrl);
    return queryParams.get('demo') !== 'false' ? 0 : 24;
  });
  const [threatFilter, setThreatFilter] = useState(queryParams.get('threat') || '');
  const [searchFilter, setSearchFilter] = useState(queryParams.get('search') || '');
  const [anomalyFilter, setAnomalyFilter] = useState(queryParams.get('anomaly') === 'true');
  const [page, setPage] = useState(Number(queryParams.get('page')) || 1);

  // Sync state back to URL query parameters
  useEffect(() => {
    const params = new URLSearchParams();
    if (!includeDemo) params.set('demo', 'false');
    if (timeRange !== (includeDemo ? 0 : 24)) params.set('hours', String(timeRange));
    if (threatFilter) params.set('threat', threatFilter);
    if (searchFilter) params.set('search', searchFilter);
    if (anomalyFilter) params.set('anomaly', 'true');
    if (page > 1) params.set('page', String(page));

    const newUrl = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}`;
    window.history.replaceState({}, '', newUrl);
  }, [includeDemo, timeRange, threatFilter, searchFilter, anomalyFilter, page]);

  // Data state
  const [health, setHealth] = useState(null);
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [attackTypes, setAttackTypes] = useState({});
  const [topIps, setTopIps] = useState([]);
  const [topCreds, setTopCreds] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isOffline, setIsOffline] = useState(false);
  const [offlineMessage, setOfflineMessage] = useState('');

  // Primary loader
  const loadAll = useCallback(async () => {
    try {
      const [h, s, e, at, ti, tc, al] = await Promise.all([
        api.getHealth(),
        api.getSummary(includeDemo, timeRange),
        api.getEvents(includeDemo, MAX_LIVE_EVENTS),
        api.getAttackTypes(includeDemo, timeRange),
        api.getTopIps(includeDemo, 10, timeRange),
        api.getTopCredentials(includeDemo, 10),
        api.getAlerts(includeDemo, timeRange),
      ]);

      if (h.error && !h.data) {
        setIsOffline(true);
        setOfflineMessage(`Health check failed: ${h.error}`);
        setLoading(false);
        return;
      }

      setIsOffline(false);
      if (h.data) setHealth(h.data);
      if (s.data) setSummary(s.data);
      if (e.data) {
        const evList = Array.isArray(e.data) ? e.data : (e.data.data || []);
        setEvents(evList.slice(0, MAX_LIVE_EVENTS));
      }
      if (at.data) setAttackTypes(at.data);
      if (ti.data) setTopIps(ti.data);
      if (tc.data) setTopCreds(tc.data);
      if (al.data) setAlerts(al.data);
    } catch (err) {
      setIsOffline(true);
      setOfflineMessage(err.message || 'Network connection failed');
    } finally {
      setLoading(false);
    }
  }, [includeDemo, timeRange]);

  useEffect(() => {
    loadAll();
    const timer = setInterval(loadAll, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [loadAll]);

  // Handle incoming live SSE events
  const handleSseMessage = useCallback((msg) => {
    try {
      const newEv = JSON.parse(msg.data);
      setEvents((prev) => {
        // Prevent duplicate by session_id
        if (prev.some((e) => e.session_id === newEv.session_id)) {
          return prev;
        }
        return [newEv, ...prev].slice(0, MAX_LIVE_EVENTS);
      });

      // Quick refresh stats on new incoming event
      api.getSummary(includeDemo, timeRange).then((res) => {
        if (res.data) setSummary(res.data);
      });
      api.getAttackTypes(includeDemo, timeRange).then((res) => {
        if (res.data) setAttackTypes(res.data);
      });
    } catch {
      // Ignore heartbeat lines or parse errors
    }
  }, [includeDemo, timeRange]);

  // Real-time SSE hook with exponential backoff & polling fallback
  const { isConnected } = useSSE(
    api.getStreamUrl(includeDemo),
    handleSseMessage,
    {
      enabled: !isOffline,
      onFallbackPoll: loadAll,
    }
  );

  const modelMode = health?.model_mode || 'synthetic';
  const score = summary?.security_score ?? 100;
  const hasDemoData = events.some((e) => e.is_demo);

  if (isOffline) {
    return <OfflineState onRetry={loadAll} message={offlineMessage} />;
  }

  if (loading) {
    return (
      <div className="app-container">
        <Header
          mode={modelMode}
          isConnected={false}
          timeRange={timeRange}
          onTimeRangeChange={setTimeRange}
          includeDemo={includeDemo}
          onIncludeDemoChange={setIncludeDemo}
        />
        <div className="loader" style={{ height: '70vh' }}>
          <Wifi size={24} className="spin" /> Initializing Honeypot SOC Dashboard...
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <Header
        mode={modelMode}
        isConnected={isConnected}
        timeRange={timeRange}
        onTimeRangeChange={(val) => {
          setTimeRange(val);
          setPage(1);
        }}
        includeDemo={includeDemo}
        onIncludeDemoChange={(val) => {
          setIncludeDemo(val);
          // When toggling demo off, switch to 24h by default; when on, default to all-time (0)
          if (!val && timeRange === 0) {
            setTimeRange(24);
          } else if (val && timeRange === 24) {
            setTimeRange(0);
          }
          setPage(1);
        }}
      />

      {/* Persistent Banners */}
      <SystemBanners modelMode={modelMode} hasDemoData={hasDemoData} />

      <main className="dashboard-grid">
        {/* ── KPI Row ── */}
        <KpiCard
          title="Total Events"
          value={summary?.total_events ?? 0}
          icon={<ActivitySquare size={18} />}
        />
        <KpiCard
          title="Critical Alerts"
          value={summary?.critical_alerts ?? 0}
          icon={<Target size={18} />}
          valueColorClass={(summary?.critical_alerts || 0) > 0 ? 'critical' : ''}
        />
        <KpiCard
          title="Anomalies"
          value={summary?.anomalous_count ?? 0}
          icon={<AlertTriangle size={18} />}
          valueColorClass={(summary?.anomalous_count || 0) > 0 ? 'high' : ''}
        />
        <KpiCard
          title="Unique IPs"
          value={summary?.unique_source_ips ?? 0}
          icon={<Users size={18} />}
        />

        {/* ── Charts Row ── */}
        <ThreatChart data={summary?.events_per_threat || {}} />
        <SecurityGauge score={score} penalties={summary?.penalty_breakdown} />

        {/* ── Attack Donut & Top IPs ── */}
        <AttackDonut data={attackTypes} />
        <div className="glass-panel mini-card" style={{ gridColumn: 'span 8' }}>
          <TopIps data={topIps} />
        </div>

        {/* ── Priority Alerts Panel ── */}
        <div style={{ gridColumn: 'span 12' }}>
          <AlertsPanel alerts={alerts} onSelectAlert={setSelectedEvent} />
        </div>

        {/* ── Top Credentials ── */}
        <div style={{ gridColumn: 'span 12' }}>
          <TopCredentials data={topCreds} />
        </div>

        {/* ── Activity Table with Filters & Pagination ── */}
        <div style={{ gridColumn: 'span 12' }}>
          <EventsTable
            events={events}
            onSelectEvent={setSelectedEvent}
            threatFilter={threatFilter}
            onThreatFilterChange={setThreatFilter}
            searchFilter={searchFilter}
            onSearchFilterChange={setSearchFilter}
            anomalyFilter={anomalyFilter}
            onAnomalyFilterChange={setAnomalyFilter}
            page={page}
            onPageChange={setPage}
            pageSize={15}
          />
        </div>
      </main>

      {/* Slide-over Detail Drawer */}
      <EventDrawer event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <Dashboard />
    </ErrorBoundary>
  );
}
