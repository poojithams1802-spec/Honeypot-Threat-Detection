import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Custom SSE hook with exponential backoff reconnect and fallback trigger.
 */
export function useSSE(streamUrl, onMessage, options = {}) {
  const { enabled = true, onFallbackPoll } = options;
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const attemptRef = useRef(0);
  const esRef = useRef(null);
  const timerRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  const onFallbackPollRef = useRef(onFallbackPoll);

  onMessageRef.current = onMessage;
  onFallbackPollRef.current = onFallbackPoll;

  const connect = useCallback(() => {
    if (!enabled || !streamUrl) return;

    if (esRef.current) {
      esRef.current.close();
    }

    try {
      const es = new EventSource(streamUrl);
      esRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
        attemptRef.current = 0;
        setReconnectAttempt(0);
      };

      es.onmessage = (event) => {
        if (onMessageRef.current) {
          onMessageRef.current(event);
        }
      };

      es.onerror = (err) => {
        setIsConnected(false);
        es.close();
        esRef.current = null;

        // Fallback polling on disconnect
        if (onFallbackPollRef.current) {
          onFallbackPollRef.current();
        }

        // Exponential backoff: min 1s, max 30s
        const attempt = attemptRef.current;
        const delay = Math.min(30000, 1000 * Math.pow(2, attempt));
        attemptRef.current = attempt + 1;
        setReconnectAttempt(attempt + 1);

        timerRef.current = setTimeout(() => {
          connect();
        }, delay);
      };
    } catch (e) {
      setIsConnected(false);
    }
  }, [enabled, streamUrl]);

  useEffect(() => {
    connect();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [connect]);

  return { isConnected, reconnectAttempt };
}
