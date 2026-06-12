// Mock lightweight-charts for Jest (browser canvas not available in jsdom)
export const ColorType = { Solid: 'Solid' };

export const LineSeries = 'Line';

export const createChart = jest.fn(() => ({
  addSeries: jest.fn(() => ({
    setData: jest.fn(),
    update: jest.fn(),
  })),
  applyOptions: jest.fn(),
  remove: jest.fn(),
  timeScale: jest.fn(() => ({
    fitContent: jest.fn(),
  })),
}));
