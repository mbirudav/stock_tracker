/**
 * @jest-environment jsdom
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatPanel from '@/components/ChatPanel';

const mockSendChat = jest.fn();
jest.mock('@/lib/api', () => ({
  api: {
    sendChat: (...args: unknown[]) => mockSendChat(...args),
  },
}));

describe('ChatPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders the welcome message', () => {
    render(<ChatPanel />);
    expect(screen.getByText(/Hello! I'm FinAlly/)).toBeInTheDocument();
  });

  it('renders message input and SEND button', () => {
    render(<ChatPanel />);
    expect(screen.getByPlaceholderText(/Ask FinAlly/)).toBeInTheDocument();
    expect(screen.getByText('SEND')).toBeInTheDocument();
  });

  it('shows user message after sending', async () => {
    mockSendChat.mockResolvedValue({
      message: 'Your portfolio looks great!',
    });

    render(<ChatPanel />);
    const input = screen.getByPlaceholderText(/Ask FinAlly/);
    await userEvent.type(input, 'How is my portfolio?');
    fireEvent.click(screen.getByText('SEND'));

    expect(screen.getByText('How is my portfolio?')).toBeInTheDocument();
  });

  it('shows loading state while awaiting response', async () => {
    let resolve: (v: unknown) => void;
    mockSendChat.mockReturnValue(new Promise(r => { resolve = r; }));

    render(<ChatPanel />);
    const input = screen.getByPlaceholderText(/Ask FinAlly/);
    await userEvent.type(input, 'Buy AAPL');
    fireEvent.click(screen.getByText('SEND'));

    expect(screen.getByText('Thinking...')).toBeInTheDocument();

    // Resolve promise
    resolve!({ message: 'Done!' });
  });

  it('shows assistant response after receiving', async () => {
    mockSendChat.mockResolvedValue({
      message: 'I bought 5 AAPL for you!',
      trades_executed: [{ ticker: 'AAPL', side: 'buy', quantity: 5, price: 192.5 }],
    });

    render(<ChatPanel />);
    const input = screen.getByPlaceholderText(/Ask FinAlly/);
    await userEvent.type(input, 'Buy 5 AAPL');
    fireEvent.click(screen.getByText('SEND'));

    await waitFor(() => {
      expect(screen.getByText('I bought 5 AAPL for you!')).toBeInTheDocument();
    });
  });

  it('shows executed trade chips', async () => {
    mockSendChat.mockResolvedValue({
      message: 'Trade executed.',
      trades_executed: [{ ticker: 'AAPL', side: 'buy', quantity: 5, price: 192.5 }],
    });

    render(<ChatPanel />);
    await userEvent.type(screen.getByPlaceholderText(/Ask FinAlly/), 'Buy AAPL');
    fireEvent.click(screen.getByText('SEND'));

    await waitFor(() => {
      expect(screen.getByText(/BUY 5 AAPL @ \$192\.50/)).toBeInTheDocument();
    });
  });

  it('clears input after sending', async () => {
    mockSendChat.mockResolvedValue({ message: 'OK' });

    render(<ChatPanel />);
    const input = screen.getByPlaceholderText(/Ask FinAlly/) as HTMLTextAreaElement;
    await userEvent.type(input, 'Hello');
    fireEvent.click(screen.getByText('SEND'));

    expect(input.value).toBe('');
  });

  it('sends on Enter key', async () => {
    mockSendChat.mockResolvedValue({ message: 'Response' });

    render(<ChatPanel />);
    const input = screen.getByPlaceholderText(/Ask FinAlly/);
    await userEvent.type(input, 'Test message{Enter}');

    await waitFor(() => {
      expect(mockSendChat).toHaveBeenCalledWith('Test message');
    });
  });
});
