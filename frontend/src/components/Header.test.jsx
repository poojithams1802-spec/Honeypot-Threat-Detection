import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Header } from './Header';

describe('Header Component', () => {
  it('renders title', () => {
    render(<Header mode="real" isConnected={true} />);
    expect(screen.getByText(/Honeypot SOC Dashboard/i)).toBeInTheDocument();
  });

  it('renders demo banner when mode is synthetic', () => {
    render(<Header mode="synthetic" isConnected={true} />);
    expect(screen.getByText(/DEMO \/ SYNTHETIC/i)).toBeInTheDocument();
  });
  
  it('renders connection status', () => {
    render(<Header mode="real" isConnected={false} />);
    expect(screen.getByText(/DISCONNECTED/i)).toBeInTheDocument();
  });
});
