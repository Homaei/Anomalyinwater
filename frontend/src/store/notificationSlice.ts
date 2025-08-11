import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { NotificationMessage } from '@/types';

interface NotificationState {
  id: string;
  message: string;
  severity: 'info' | 'warning' | 'error' | 'success';
  timestamp: number;
  data?: Record<string, any>;
}

interface NotificationsState {
  notifications: NotificationState[];
  maxNotifications: number;
}

const initialState: NotificationsState = {
  notifications: [],
  maxNotifications: 10,
};

const notificationSlice = createSlice({
  name: 'notifications',
  initialState,
  reducers: {
    addNotification: (state, action: PayloadAction<NotificationMessage>) => {
      const notification: NotificationState = {
        id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
        message: action.payload.message,
        severity: action.payload.severity,
        timestamp: Date.now(),
        data: action.payload.data,
      };

      // Add to beginning of array
      state.notifications.unshift(notification);

      // Keep only the most recent notifications
      if (state.notifications.length > state.maxNotifications) {
        state.notifications = state.notifications.slice(0, state.maxNotifications);
      }
    },

    removeNotification: (state, action: PayloadAction<string>) => {
      state.notifications = state.notifications.filter(
        (notification) => notification.id !== action.payload
      );
    },

    clearNotifications: (state) => {
      state.notifications = [];
    },

    markAsRead: (state, action: PayloadAction<string>) => {
      const notification = state.notifications.find(n => n.id === action.payload);
      if (notification) {
        notification.data = { ...notification.data, read: true };
      }
    },

    setMaxNotifications: (state, action: PayloadAction<number>) => {
      state.maxNotifications = action.payload;
      if (state.notifications.length > action.payload) {
        state.notifications = state.notifications.slice(0, action.payload);
      }
    },
  },
});

export const {
  addNotification,
  removeNotification,
  clearNotifications,
  markAsRead,
  setMaxNotifications,
} = notificationSlice.actions;

export default notificationSlice.reducer;