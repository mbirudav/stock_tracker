/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TradeBar from '@/components/TradeBar';

// Mock the api
const mockExecuteTrade = jest.fn();
jest.mock('@/lib/api', () => ({
  api: {
    executeTrade: (...args: unknown[]) => mockExecuteTrade(...args),
  },
}));

describe('TradeBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders ticker and quantity inputs', () => {
    render(<TradeBar />);
    expect(screen.getByPlaceholderText('TICKER')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('QTY')).toBeInTheDocument();
  });

  it('renders BUY and SELL buttons', () => {
    render(<TradeBar />);
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('SELL')).toBeInTheDocument();
  });

  it('calls executeTrade with correct body on BUY click', async () => {
    mockExecuteTrade.mockResolvedValue({
      success: true,
      trade: { ticker: 'AAPL', side: 'buy', quantity: 10, price: 192.5, executed_at: '' },
    });

    render(<TradeBar />);

    const tickerInput = screen.getByPlaceholderText('TICKER');
    const qtyInput = screen.getByPlaceholderText('QTY');
    const buyButton = screen.getByText('BUY');

    await userEvent.type(tickerInput, 'AAPL');
    await userEvent.type(qtyInput, '10');
    fireEvent.click(buyButton);

    await waitFor(() => {
      expect(mockExecuteTrade).toHaveBeenCalledWith({
        ticker: 'AAPL',
        quantity: 10,
        side: 'buy',
      });
    });
  });

  it('calls executeTrade with correct body on SELL click', async () => {
    mockExecuteTrade.mockResolvedValue({
      success: true,
      trade: { ticker: 'TSLA', side: 'sell', quantity: 5, price: 250.0, executed_at: '' },
    });

    render(<TradeBar />);

    const tickerInput = screen.getByPlaceholderText('TICKER');
    const qtyInput = screen.getByPlaceholderText('QTY');
    const sellButton = screen.getByText('SELL');

    await userEvent.type(tickerInput, 'TSLA');
    await userEvent.type(qtyInput, '5');
    fireEvent.click(sellButton);

    await waitFor(() => {
      expect(mockExecuteTrade).toHaveBeenCalledWith({
        ticker: 'TSLA',
        quantity: 5,
        side: 'sell',
      });
    });
  });

  it('shows error message on trade failure', async () => {
    mockExecuteTrade.mockRejectedValue(new Error('Insufficient funds'));
    render(<TradeBar />);

    await userEvent.type(screen.getByPlaceholderText('TICKER'), 'AAPL');
    await userEvent.type(screen.getByPlaceholderText('QTY'), '10');
    fireEvent.click(screen.getByText('BUY'));

    await waitFor(() => {
      expect(screen.getByText('Insufficient funds')).toBeInTheDocument();
    });
  });

  it('shows validation error when ticker is empty', async () => {
    render(<TradeBar />);
    await userEvent.type(screen.getByPlaceholderText('QTY'), '10');
    fireEvent.click(screen.getByText('BUY'));
    expect(screen.getByText('Enter a ticker symbol')).toBeInTheDocument();
  });

  it('shows validation error when quantity is invalid', async () => {
    render(<TradeBar />);
    await userEvent.type(screen.getByPlaceholderText('TICKER'), 'AAPL');
    fireEvent.click(screen.getByText('BUY'));
    expect(screen.getByText('Enter a valid quantity')).toBeInTheDocument();
  });

  it('pre-fills ticker from selectedTicker prop', () => {
    render(<TradeBar selectedTicker="NVDA" />);
    const tickerInput = screen.getByPlaceholderText('TICKER') as HTMLInputElement;
    expect(tickerInput.value).toBe('NVDA');
  });
});
