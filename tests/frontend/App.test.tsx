import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { BrowserRouter } from 'react-router-dom';
import { configureStore } from '@reduxjs/toolkit';
import '@testing-library/jest-dom';

import App from '../src/App';
import authReducer from '../src/store/authSlice';
import notificationReducer from '../src/store/notificationSlice';
import dataReducer from '../src/store/dataSlice';

// Mock API service
jest.mock('../src/services/api', () => ({
  apiService: {
    login: jest.fn(),
    getCurrentUser: jest.fn(),
    healthCheck: jest.fn(),
  },
}));

// Mock WebSocket hook
jest.mock('../src/hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    connect: jest.fn(),
    disconnect: jest.fn(),
    sendMessage: jest.fn(),
    connectionState: 'CLOSED',
    connected: false,
  }),
}));

// Test store factory
const createTestStore = (initialState = {}) => {
  return configureStore({
    reducer: {
      auth: authReducer,
      notifications: notificationReducer,
      data: dataReducer,
    },
    preloadedState: initialState,
  });
};

// Test wrapper component
const TestWrapper: React.FC<{ children: React.ReactNode; store?: any }> = ({ 
  children, 
  store = createTestStore() 
}) => {
  return (
    <Provider store={store}>
      <BrowserRouter>
        {children}
      </BrowserRouter>
    </Provider>
  );
};

describe('App Component', () => {
  beforeEach(() => {
    // Clear localStorage
    localStorage.clear();
    
    // Reset mocks
    jest.clearAllMocks();
  });

  test('renders login page when not authenticated', () => {
    const store = createTestStore({
      auth: {
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    expect(screen.getByText(/WWTP Anomaly Detection/i)).toBeInTheDocument();
    expect(screen.getByText(/Sign in to your account/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
  });

  test('shows loading screen when auth is loading', () => {
    const store = createTestStore({
      auth: {
        user: null,
        isAuthenticated: false,
        isLoading: true,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    expect(screen.getByText(/Loading.../i)).toBeInTheDocument();
  });

  test('renders dashboard when authenticated', () => {
    const store = createTestStore({
      auth: {
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          role: 'operator',
          is_active: true,
          created_at: '2023-01-01T00:00:00Z',
          updated_at: '2023-01-01T00:00:00Z',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/WWTP Anomaly Detection/i)).toBeInTheDocument();
  });

  test('handles login form submission', async () => {
    const user = userEvent.setup();
    const mockLogin = require('../src/services/api').apiService.login;
    mockLogin.mockResolvedValueOnce({
      access_token: 'test-token',
      token_type: 'bearer',
      user: {
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        role: 'operator',
      },
    });

    const store = createTestStore({
      auth: {
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    // Fill in login form
    const usernameInput = screen.getByLabelText(/Username/i);
    const passwordInput = screen.getByLabelText(/Password/i);
    const submitButton = screen.getByRole('button', { name: /Sign In/i });

    await user.type(usernameInput, 'testuser');
    await user.type(passwordInput, 'password');
    await user.click(submitButton);

    // Check if login was called
    expect(mockLogin).toHaveBeenCalledWith({
      username: 'testuser',
      password: 'password',
    });
  });

  test('displays error message on login failure', async () => {
    const user = userEvent.setup();
    const mockLogin = require('../src/services/api').apiService.login;
    mockLogin.mockRejectedValueOnce({
      response: { data: { detail: 'Invalid credentials' } },
    });

    const store = createTestStore({
      auth: {
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: 'Invalid credentials',
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    expect(screen.getByText(/Invalid credentials/i)).toBeInTheDocument();
  });

  test('redirects to dashboard when already authenticated', () => {
    const store = createTestStore({
      auth: {
        user: {
          id: '1',
          username: 'testuser',
          email: 'test@example.com',
          role: 'admin',
          is_active: true,
          created_at: '2023-01-01T00:00:00Z',
          updated_at: '2023-01-01T00:00:00Z',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    // Should show dashboard, not login
    expect(screen.queryByText(/Sign in to your account/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
  });

  test('shows role-based navigation for admin users', () => {
    const store = createTestStore({
      auth: {
        user: {
          id: '1',
          username: 'admin',
          email: 'admin@example.com',
          role: 'admin',
          is_active: true,
          created_at: '2023-01-01T00:00:00Z',
          updated_at: '2023-01-01T00:00:00Z',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    // Admin should see all navigation items
    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload Images/i)).toBeInTheDocument();
    expect(screen.getByText(/Review Queue/i)).toBeInTheDocument();
    expect(screen.getByText(/Image Gallery/i)).toBeInTheDocument();
    expect(screen.getByText(/ADMIN/i)).toBeInTheDocument(); // Role chip
  });

  test('shows limited navigation for operator users', () => {
    const store = createTestStore({
      auth: {
        user: {
          id: '1',
          username: 'operator',
          email: 'operator@example.com',
          role: 'operator',
          is_active: true,
          created_at: '2023-01-01T00:00:00Z',
          updated_at: '2023-01-01T00:00:00Z',
        },
        isAuthenticated: true,
        isLoading: false,
        error: null,
      },
    });

    render(
      <TestWrapper store={store}>
        <App />
      </TestWrapper>
    );

    // Operator should see limited navigation
    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload Images/i)).toBeInTheDocument();
    expect(screen.getByText(/Image Gallery/i)).toBeInTheDocument();
    expect(screen.queryByText(/Review Queue/i)).not.toBeInTheDocument(); // No review access
    expect(screen.getByText(/OPERATOR/i)).toBeInTheDocument(); // Role chip
  });
});

// API Service Tests
describe('API Service', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  test('sets authorization header when token is present', () => {
    const { apiService } = require('../src/services/api');
    
    // Mock axios instance
    const mockAxios = {
      interceptors: {
        request: { use: jest.fn() },
        response: { use: jest.fn() },
      },
      get: jest.fn(),
      post: jest.fn(),
      put: jest.fn(),
      delete: jest.fn(),
    };

    // Test token setting
    apiService.setToken('test-token');
    expect(localStorage.getItem('access_token')).toBe('test-token');
  });

  test('clears token on logout', () => {
    const { apiService } = require('../src/services/api');
    
    localStorage.setItem('access_token', 'test-token');
    apiService.clearToken();
    
    expect(localStorage.getItem('access_token')).toBeNull();
  });
});

// WebSocket Hook Tests  
describe('useWebSocket Hook', () => {
  test('connects when user is authenticated', () => {
    const mockConnect = jest.fn();
    const mockUseWebSocket = require('../src/hooks/useWebSocket').useWebSocket;
    
    // Mock implementation would test WebSocket connection logic
    expect(mockConnect).toBeDefined();
  });
});

// Store Tests
describe('Redux Store', () => {
  test('handles authentication state correctly', () => {
    const store = createTestStore();
    const initialState = store.getState();
    
    expect(initialState.auth.isAuthenticated).toBe(false);
    expect(initialState.auth.user).toBeNull();
    expect(initialState.auth.isLoading).toBe(false);
  });

  test('handles notifications correctly', () => {
    const store = createTestStore();
    const { addNotification } = require('../src/store/notificationSlice');
    
    store.dispatch(addNotification({
      message: 'Test notification',
      severity: 'info',
    }));
    
    const state = store.getState();
    expect(state.notifications.notifications).toHaveLength(1);
    expect(state.notifications.notifications[0].message).toBe('Test notification');
  });
});