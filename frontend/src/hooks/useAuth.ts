import { useSelector, useDispatch } from 'react-redux';
import { useCallback, useEffect } from 'react';
import { RootState } from '@/store';
import { login, logout, getCurrentUser, clearError } from '@/store/authSlice';
import { LoginRequest } from '@/types';

export const useAuth = () => {
  const dispatch = useDispatch();
  const { user, isAuthenticated, isLoading, error } = useSelector(
    (state: RootState) => state.auth
  );

  const handleLogin = useCallback(async (credentials: LoginRequest) => {
    return dispatch(login(credentials)).unwrap();
  }, [dispatch]);

  const handleLogout = useCallback(async () => {
    return dispatch(logout()).unwrap();
  }, [dispatch]);

  const refreshUser = useCallback(async () => {
    return dispatch(getCurrentUser()).unwrap();
  }, [dispatch]);

  const clearAuthError = useCallback(() => {
    dispatch(clearError());
  }, [dispatch]);

  // Check if user has specific permission
  const hasPermission = useCallback((permission: string) => {
    if (!user || !isAuthenticated) return false;

    // Admin has all permissions
    if (user.role === 'admin') return true;

    // Define role-based permissions
    const permissions = {
      admin: ['*'], // All permissions
      reviewer: ['read', 'review', 'update_review'],
      operator: ['read', 'upload'],
    };

    const userPermissions = permissions[user.role] || [];
    return userPermissions.includes('*') || userPermissions.includes(permission);
  }, [user, isAuthenticated]);

  // Check if user has specific role
  const hasRole = useCallback((role: string | string[]) => {
    if (!user || !isAuthenticated) return false;

    if (Array.isArray(role)) {
      return role.includes(user.role);
    }
    return user.role === role;
  }, [user, isAuthenticated]);

  // Initialize auth state on app start
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token && !user && !isLoading) {
      dispatch(getCurrentUser());
    }
  }, [dispatch, user, isLoading]);

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    login: handleLogin,
    logout: handleLogout,
    refreshUser,
    clearError: clearAuthError,
    hasPermission,
    hasRole,
  };
};