import React from 'react';
import { AlertOctagon, RotateCw } from 'lucide-react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="offline-screen" data-testid="error-boundary-fallback">
          <div className="glass-panel offline-card">
            <AlertOctagon size={48} className="text-danger" />
            <h2>Application Error</h2>
            <p>An unexpected error occurred while rendering the dashboard.</p>
            <pre className="error-detail">{this.state.error?.message || 'Unknown error'}</pre>
            <button className="btn btn-primary" onClick={this.handleReset}>
              <RotateCw size={16} /> Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
