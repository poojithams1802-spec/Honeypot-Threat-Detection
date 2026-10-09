import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { KpiCard } from './KpiCard';

describe('KpiCard Component', () => {
  it('renders title and value', () => {
    render(<KpiCard title="Total Events" value={42} />);
    expect(screen.getByText(/Total Events/i)).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('applies color class when specified', () => {
    const { container } = render(
      <KpiCard title="Critical Alerts" value={5} valueColorClass="text-danger" />
    );
    const valueEl = container.querySelector('.text-danger');
    expect(valueEl).toBeInTheDocument();
    expect(valueEl.textContent).toBe('5');
  });
});
