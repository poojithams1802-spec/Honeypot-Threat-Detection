import React from 'react';

export function TopCredentials({ data }) {
  const usernames = data?.usernames || [];
  const passwords = data?.passwords || [];

  if (usernames.length === 0 && passwords.length === 0) {
    return (
      <div className="glass-panel mini-card">
        <div className="card-header"><h3 className="card-title">Top Credentials</h3></div>
        <div className="loader">No data</div>
      </div>
    );
  }

  return (
    <div className="glass-panel mini-card">
      <div className="card-header"><h3 className="card-title">Top Credentials</h3></div>
      <div className="creds-grid">
        <div>
          <h4 className="creds-subtitle">Usernames</h4>
          {usernames.length === 0 ? (
            <p className="creds-empty">None captured</p>
          ) : (
            <ul className="creds-list">
              {usernames.map((u, i) => (
                <li key={i} className="creds-item">
                  <span className="creds-name">{u.username}</span>
                  <span className="creds-count">{u.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4 className="creds-subtitle">Passwords</h4>
          {passwords.length === 0 ? (
            <p className="creds-empty">None captured</p>
          ) : (
            <ul className="creds-list">
              {passwords.map((p, i) => (
                <li key={i} className="creds-item">
                  <span className="creds-name">{p.password}</span>
                  <span className="creds-count">{p.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
