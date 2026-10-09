# Known Limitations and Future Work

While Honeypot-ML provides a robust foundation for ML-based threat detection on honeypot data, several limitations exist in the current implementation.

## Current Limitations

1. **Synthetic Data Dependency**
   The current ML model (`synthetic_threat_classifier.joblib`) was trained on synthetic data. Real-world threat vectors may differ significantly from the synthetic distribution.
   - *Mitigation*: The UI explicitly flags this with a "SYNTHETIC" banner.

2. **Session Identification**
   Sessions are tracked by `session_id` provided by Cowrie logs. If a threat actor obscures their session (e.g., fragmented attacks over prolonged periods), the IP-level aggregation might miss complex, slow attacks.

3. **Database Scalability**
   The development database uses SQLite. While sufficient for local development and student projects, it will suffer from lock contention (`OperationalError: database is locked`) under high concurrency.
   - *Mitigation*: The codebase uses SQLAlchemy and can be easily migrated to PostgreSQL.

4. **Security & Authentication**
   The dashboard and APIs are currently unauthenticated. Anyone with access to the port can view the honeypot data.
   - *Mitigation*: Implement OAuth2 or JWT-based authentication in FastAPI.

5. **Frontend Testing**
   E2E testing is minimal. The UI relies primarily on React component tests using Vitest. Full Cypress or Playwright tests would be ideal for production.

## Future Enhancements
- Dockerize the entire application for single-command deployment.
- Integrate real-time alerting (e.g., Slack/Discord webhooks) on critical threats.
- Implement more robust IP reputation lookups via external APIs (e.g., VirusTotal, AbuseIPDB).
