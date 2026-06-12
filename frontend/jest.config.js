const nextJest = require('next/jest');

const createJestConfig = nextJest({
  dir: './',
});

const customJestConfig = {
  testEnvironment: 'jest-environment-jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
    // Mock lightweight-charts since it requires browser canvas
    '^lightweight-charts$': '<rootDir>/__mocks__/lightweight-charts.ts',
  },
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  testMatch: ['**/__tests__/**/*.test.{ts,tsx}'],
};

module.exports = createJestConfig(customJestConfig);
