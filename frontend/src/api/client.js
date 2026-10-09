const BASE_URL = '/api';

export async function fetchJSON(url, options = {}) {
  try {
    const response = await fetch(`${BASE_URL}${url}`, {
      ...options,
      headers: {
        'Accept': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return { data: await response.json(), error: null };
  } catch (error) {
    return { data: null, error: error.message || 'Network error' };
  }
}

export const api = {
  getHealth: () => fetchJSON('/health'),

  getSummary: (includeDemo = true, hours = 0) =>
    fetchJSON(`/stats/summary?include_demo=${includeDemo}&hours=${hours}`),

  getEvents: (includeDemo = true, limit = 200, params = {}) => {
    const query = new URLSearchParams({
      include_demo: includeDemo,
      page_size: limit,
      ...params,
    });
    return fetchJSON(`/events?${query.toString()}`);
  },

  getEvent: (sessionId) => fetchJSON(`/events/${encodeURIComponent(sessionId)}`),

  getAttackTypes: (includeDemo = true, hours = 0) =>
    fetchJSON(`/stats/attack-types?include_demo=${includeDemo}&hours=${hours}`),

  getTimeline: (includeDemo = true, hours = 0, bucketMinutes = 60) =>
    fetchJSON(`/stats/timeline?include_demo=${includeDemo}&hours=${hours}&bucket_minutes=${bucketMinutes}`),

  getTopIps: (includeDemo = true, limit = 10, hours = 0) =>
    fetchJSON(`/stats/top-ips?include_demo=${includeDemo}&limit=${limit}&hours=${hours}`),

  getTopCredentials: (includeDemo = true, limit = 10) =>
    fetchJSON(`/stats/top-credentials?include_demo=${includeDemo}&limit=${limit}`),

  getAlerts: (includeDemo = true, hours = 0) =>
    fetchJSON(`/alerts?include_demo=${includeDemo}&hours=${hours}`),

  getIngestStatus: () => fetchJSON('/ingest/status'),

  getStreamUrl: (includeDemo = true) => `${BASE_URL}/events/stream?include_demo=${includeDemo}`,
};
