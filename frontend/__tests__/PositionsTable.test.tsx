/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import PositionsTable from '@/components/PositionsTable';
import { Portfolio } from '@/lib/api';

const mockPortfolioWithPositions: Portfolio = {
  cash_balance: 7500,
  total_value: 10500,
  positions: [
    {
      ticker: 'AAPL',
      quantity: 10,
      avg_cost: 190.0,
      current_price: 200.0,
      market_value: 2000.0,
      unrealized_pnl: 100.0,
      pnl_pct: 5.26,
    },
    {
      ticker: 'TSLA',
      quantity: 5,
      avg_cost: 260.0,
      current_price: 240.0,
      market_value: 1200.0,
      unrealized_pnl: -100.0,
      pnl_pct: -7.69,
    },
  ],
};

describe('PositionsTable', () => {
  it('renders positions table headers', () => {
    render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    expect(screen.getByText('TICKER')).toBeInTheDocument();
    expect(screen.getByText('QTY')).toBeInTheDocument();
    expect(screen.getByText('AVG COST')).toBeInTheDocument();
    expect(screen.getByText('CURRENT')).toBeInTheDocument();
  });

  it('renders all positions', () => {
    render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByText('TSLA')).toBeInTheDocument();
  });

  it('shows positive P&L in green', () => {
    const { container } = render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    // Find the P&L cell for AAPL (positive)
    const greenElements = container.querySelectorAll('[style*="color: rgb(34, 197, 94)"], [style*="color:#22c55e"]');
    // At minimum AAPL P&L should be green
    const pnlCell = screen.getByText('+$100.00');
    expect(pnlCell).toHaveStyle({ color: '#22c55e' });
  });

  it('shows negative P&L in red', () => {
    render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    const pnlCell = screen.getByText('-$100.00');
    expect(pnlCell).toHaveStyle({ color: '#ef4444' });
  });

  it('shows correct P&L percentages', () => {
    render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    expect(screen.getByText('+5.26%')).toBeInTheDocument();
    expect(screen.getByText('-7.69%')).toBeInTheDocument();
  });

  it('shows "No open positions" when portfolio has no positions', () => {
    const emptyPortfolio: Portfolio = {
      cash_balance: 10000,
      total_value: 10000,
      positions: [],
    };
    render(<PositionsTable portfolio={emptyPortfolio} />);
    expect(screen.getByText('No open positions')).toBeInTheDocument();
  });

  it('renders with null portfolio gracefully', () => {
    render(<PositionsTable portfolio={null} />);
    expect(screen.getByText('No open positions')).toBeInTheDocument();
  });

  it('shows quantities correctly', () => {
    render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows avg cost and current price', () => {
    render(<PositionsTable portfolio={mockPortfolioWithPositions} />);
    expect(screen.getByText('$190.00')).toBeInTheDocument();
    expect(screen.getByText('$200.00')).toBeInTheDocument();
    expect(screen.getByText('$260.00')).toBeInTheDocument();
    expect(screen.getByText('$240.00')).toBeInTheDocument();
  });
});
