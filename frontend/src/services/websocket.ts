import { WebSocketMessage, NotificationMessage } from '@/types';

export interface WebSocketConfig {
  url: string;
  token: string;
  onMessage?: (message: WebSocketMessage) => void;
  onNotification?: (notification: NotificationMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

export class WebSocketService {
  private ws: WebSocket | null = null;
  private config: WebSocketConfig;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectInterval = 5000; // 5 seconds
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private isManualClose = false;
  private isConnected = false;

  constructor(config: WebSocketConfig) {
    this.config = config;
  }

  connect(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    this.isManualClose = false;
    const wsUrl = `${this.config.url}?token=${encodeURIComponent(this.config.token)}`;
    
    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventHandlers();
    } catch (error) {
      console.error('WebSocket connection error:', error);
      this.config.onError?.(error as Event);
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.isManualClose = true;
    
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect');
      this.ws = null;
    }

    this.isConnected = false;
    this.reconnectAttempts = 0;
  }

  send(message: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn('WebSocket is not connected. Message not sent:', message);
    }
  }

  private setupEventHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.isConnected = true;
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.config.onConnect?.();
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.handleMessage(message);
      } catch (error) {
        console.error('Error parsing WebSocket message:', error);
      }
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket disconnected:', event.code, event.reason);
      this.isConnected = false;
      
      if (this.heartbeatInterval) {
        clearInterval(this.heartbeatInterval);
        this.heartbeatInterval = null;
      }

      this.config.onDisconnect?.();

      // Only attempt to reconnect if it wasn't a manual close
      if (!this.isManualClose && event.code !== 1000) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this.config.onError?.(error);
    };
  }

  private handleMessage(message: WebSocketMessage): void {
    console.log('WebSocket message received:', message);

    switch (message.type) {
      case 'connection_established':
        console.log('WebSocket connection established for user:', message.data.username);
        break;

      case 'heartbeat_ack':
        // Heartbeat acknowledged
        break;

      case 'notification':
        this.config.onNotification?.({
          message: message.data.message,
          severity: message.data.severity || 'info',
          data: message.data.data || {}
        });
        break;

      case 'new_detection':
        this.config.onNotification?.({
          message: `New ${message.data.is_anomaly ? 'anomaly' : 'normal'} detection (confidence: ${(message.data.confidence * 100).toFixed(1)}%)`,
          severity: message.data.is_anomaly ? 'warning' : 'info',
          data: message.data
        });
        break;

      case 'review_completed':
        this.config.onNotification?.({
          message: `Review completed: ${message.data.verdict}`,
          severity: 'success',
          data: message.data
        });
        break;

      case 'system_alert':
        this.config.onNotification?.({
          message: message.data.message,
          severity: 'error',
          data: message.data
        });
        break;

      default:
        // Pass through any other message types
        this.config.onMessage?.(message);
    }
  }

  private startHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }

    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected) {
        this.send({
          type: 'heartbeat',
          timestamp: new Date().toISOString()
        });
      }
    }, 30000); // Send heartbeat every 30 seconds
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff

    console.log(`Scheduling WebSocket reconnection attempt ${this.reconnectAttempts} in ${delay}ms`);

    setTimeout(() => {
      if (!this.isManualClose) {
        console.log(`Attempting WebSocket reconnection (attempt ${this.reconnectAttempts})`);
        this.connect();
      }
    }, delay);
  }

  get connectionState(): string {
    if (!this.ws) return 'CLOSED';
    
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return 'CONNECTING';
      case WebSocket.OPEN:
        return 'OPEN';
      case WebSocket.CLOSING:
        return 'CLOSING';
      case WebSocket.CLOSED:
        return 'CLOSED';
      default:
        return 'UNKNOWN';
    }
  }

  get connected(): boolean {
    return this.isConnected && this.ws?.readyState === WebSocket.OPEN;
  }
}

// Factory function for creating WebSocket service
export const createWebSocketService = (config: WebSocketConfig): WebSocketService => {
  return new WebSocketService(config);
};