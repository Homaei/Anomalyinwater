export interface User {
  id: string;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: 'admin' | 'reviewer' | 'operator';
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login?: string;
}

export interface Image {
  id: string;
  filename: string;
  original_filename: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  width?: number;
  height?: number;
  uploaded_by: string;
  upload_timestamp: string;
  processing_status: 'pending' | 'processing' | 'completed' | 'failed';
  metadata: Record<string, any>;
  checksum: string;
}

export interface Detection {
  id: string;
  image_id: string;
  model_version: string;
  confidence_score: number;
  is_anomaly: boolean;
  anomaly_type?: string;
  bounding_box?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  features: Record<string, any>;
  processing_time_ms?: number;
  detected_at: string;
}

export interface Review {
  id: string;
  detection_id: string;
  reviewer_id: string;
  review_status: 'pending' | 'approved' | 'rejected';
  human_verdict?: 'true_positive' | 'false_positive' | 'true_negative' | 'false_negative';
  confidence_level?: number;
  notes?: string;
  reviewed_at: string;
  review_duration_seconds?: number;
}

export interface ReviewWithDetails extends Review {
  detection: Detection;
  image: Image;
  reviewer: User;
}

export interface DetectionWithReview extends Detection {
  image: Image;
  reviews: Review[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface ReviewStats {
  total_pending: number;
  total_approved: number;
  total_rejected: number;
  avg_review_time?: number;
  reviewer_stats: Record<string, Record<string, number>>;
}

export interface WebSocketMessage {
  type: string;
  data: Record<string, any>;
  timestamp: string;
}

export interface NotificationMessage {
  message: string;
  severity: 'info' | 'warning' | 'error' | 'success';
  data?: Record<string, any>;
}

export interface UploadProgress {
  file: File;
  progress: number;
  status: 'uploading' | 'completed' | 'error';
  error?: string;
}

export interface DashboardStats {
  total_images: number;
  total_detections: number;
  anomaly_count: number;
  pending_reviews: number;
  avg_confidence: number;
  processing_accuracy?: number;
}

export interface ChartData {
  labels: string[];
  datasets: {
    label: string;
    data: number[];
    backgroundColor?: string | string[];
    borderColor?: string | string[];
    borderWidth?: number;
  }[];
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ApiError {
  error: string;
  detail?: string;
  timestamp: string;
}