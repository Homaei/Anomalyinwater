import { useEffect, useCallback, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '@/store';
import { addNotification } from '@/store/notificationSlice';
import { addNewDetection, updateImageStatus, updateReviewInList } from '@/store/dataSlice';
import { WebSocketService, createWebSocketService } from '@/services/websocket';
import { WebSocketMessage, NotificationMessage } from '@/types';

const WS_URL = process.env.REACT_APP_WS_URL || 'ws://localhost/ws';

export const useWebSocket = () => {
  const dispatch = useDispatch();
  const { user, isAuthenticated } = useSelector((state: RootState) => state.auth);
  const wsRef = useRef<WebSocketService | null>(null);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    console.log('WebSocket message received:', message);

    switch (message.type) {
      case 'new_detection':
        dispatch(addNewDetection(message.data));
        break;

      case 'image_status_update':
        dispatch(updateImageStatus({
          id: message.data.image_id,
          status: message.data.status
        }));
        break;

      case 'review_updated':
        dispatch(updateReviewInList(message.data));
        break;

      default:
        console.log('Unhandled WebSocket message type:', message.type);
    }
  }, [dispatch]);

  const handleNotification = useCallback((notification: NotificationMessage) => {
    dispatch(addNotification(notification));
  }, [dispatch]);

  const handleConnect = useCallback(() => {
    console.log('WebSocket connected');
    dispatch(addNotification({
      message: 'Connected to real-time updates',
      severity: 'success'
    }));
  }, [dispatch]);

  const handleDisconnect = useCallback(() => {
    console.log('WebSocket disconnected');
    dispatch(addNotification({
      message: 'Disconnected from real-time updates',
      severity: 'warning'
    }));
  }, [dispatch]);

  const handleError = useCallback((error: Event) => {
    console.error('WebSocket error:', error);
    dispatch(addNotification({
      message: 'WebSocket connection error',
      severity: 'error'
    }));
  }, [dispatch]);

  const connect = useCallback(() => {
    if (!isAuthenticated || !user) {
      console.log('User not authenticated, skipping WebSocket connection');
      return;
    }

    const token = localStorage.getItem('access_token');
    if (!token) {
      console.log('No access token found, skipping WebSocket connection');
      return;
    }

    if (wsRef.current?.connected) {
      console.log('WebSocket already connected');
      return;
    }

    console.log('Connecting to WebSocket...');
    wsRef.current = createWebSocketService({
      url: WS_URL,
      token,
      onMessage: handleMessage,
      onNotification: handleNotification,
      onConnect: handleConnect,
      onDisconnect: handleDisconnect,
      onError: handleError,
    });

    wsRef.current.connect();
  }, [isAuthenticated, user, handleMessage, handleNotification, handleConnect, handleDisconnect, handleError]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.disconnect();
      wsRef.current = null;
    }
  }, []);

  const sendMessage = useCallback((message: any) => {
    if (wsRef.current?.connected) {
      wsRef.current.send(message);
    } else {
      console.warn('WebSocket not connected, cannot send message:', message);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated && user) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [isAuthenticated, user, connect, disconnect]);

  return {
    connect,
    disconnect,
    sendMessage,
    connectionState: wsRef.current?.connectionState || 'CLOSED',
    connected: wsRef.current?.connected || false,
  };
};