import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { 
  User, 
  Image, 
  Detection, 
  Review, 
  ReviewWithDetails, 
  DetectionWithReview,
  PaginatedResponse,
  ReviewStats,
  LoginRequest,
  LoginResponse,
  DashboardStats,
  UploadProgress
} from '@/types';

// API Configuration
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost/api';

class ApiService {
  private api: AxiosInstance;
  private token: string | null = null;

  constructor() {
    this.api = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor to add auth token
    this.api.interceptors.request.use(
      (config) => {
        if (this.token) {
          config.headers.Authorization = `Bearer ${this.token}`;
        }
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // Response interceptor for error handling
    this.api.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          // Token expired or invalid
          this.clearToken();
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );

    // Load token from localStorage
    this.loadToken();
  }

  // Token management
  setToken(token: string): void {
    this.token = token;
    localStorage.setItem('access_token', token);
  }

  clearToken(): void {
    this.token = null;
    localStorage.removeItem('access_token');
  }

  private loadToken(): void {
    const token = localStorage.getItem('access_token');
    if (token) {
      this.token = token;
    }
  }

  // Authentication endpoints
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await this.api.post<LoginResponse>('/auth/login', credentials);
    this.setToken(response.data.access_token);
    return response.data;
  }

  async logout(): Promise<void> {
    try {
      await this.api.post('/auth/logout');
    } finally {
      this.clearToken();
    }
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.api.get<User>('/auth/me');
    return response.data;
  }

  // Image endpoints
  async uploadImages(
    files: File[],
    onProgress?: (progress: UploadProgress[]) => void
  ): Promise<Image[]> {
    const uploadPromises = files.map(async (file, index) => {
      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await this.api.post<Image>('/upload/images', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
              const progress = (progressEvent.loaded / progressEvent.total) * 100;
              onProgress([{
                file,
                progress,
                status: 'uploading'
              }]);
            }
          },
        });

        if (onProgress) {
          onProgress([{
            file,
            progress: 100,
            status: 'completed'
          }]);
        }

        return response.data;
      } catch (error) {
        if (onProgress) {
          onProgress([{
            file,
            progress: 0,
            status: 'error',
            error: error instanceof Error ? error.message : 'Upload failed'
          }]);
        }
        throw error;
      }
    });

    return Promise.all(uploadPromises);
  }

  async getImages(params: {
    page?: number;
    size?: number;
    status?: string;
  } = {}): Promise<PaginatedResponse<Image>> {
    const response = await this.api.get<PaginatedResponse<Image>>('/upload/images', {
      params
    });
    return response.data;
  }

  async getImage(imageId: string): Promise<Image> {
    const response = await this.api.get<Image>(`/upload/images/${imageId}`);
    return response.data;
  }

  // Detection endpoints
  async getDetections(params: {
    page?: number;
    size?: number;
    is_anomaly?: boolean;
    min_confidence?: number;
    unreviewed_only?: boolean;
  } = {}): Promise<PaginatedResponse<DetectionWithReview>> {
    const response = await this.api.get<PaginatedResponse<DetectionWithReview>>('/review/detections', {
      params
    });
    return response.data;
  }

  async getDetection(detectionId: string): Promise<DetectionWithReview> {
    const response = await this.api.get<DetectionWithReview>(`/review/detections/${detectionId}`);
    return response.data;
  }

  // Review endpoints
  async getReviews(params: {
    page?: number;
    size?: number;
    status?: string;
    reviewer_id?: string;
    sort_by?: string;
    sort_order?: string;
  } = {}): Promise<PaginatedResponse<ReviewWithDetails>> {
    const response = await this.api.get<PaginatedResponse<ReviewWithDetails>>('/review/reviews', {
      params
    });
    return response.data;
  }

  async getReview(reviewId: string): Promise<ReviewWithDetails> {
    const response = await this.api.get<ReviewWithDetails>(`/review/reviews/${reviewId}`);
    return response.data;
  }

  async createReview(data: {
    detection_id: string;
    review_status?: string;
    human_verdict?: string;
    confidence_level?: number;
    notes?: string;
  }): Promise<Review> {
    const response = await this.api.post<Review>('/review/reviews', data);
    return response.data;
  }

  async updateReview(reviewId: string, data: {
    review_status?: string;
    human_verdict?: string;
    confidence_level?: number;
    notes?: string;
    review_duration_seconds?: number;
  }): Promise<Review> {
    const response = await this.api.put<Review>(`/review/reviews/${reviewId}`, data);
    return response.data;
  }

  async deleteReview(reviewId: string): Promise<void> {
    await this.api.delete(`/review/reviews/${reviewId}`);
  }

  async getPendingReviews(limit: number = 50): Promise<ReviewWithDetails[]> {
    const response = await this.api.get<ReviewWithDetails[]>('/review/reviews/pending', {
      params: { limit }
    });
    return response.data;
  }

  async assignReview(detectionId: string): Promise<Review> {
    const response = await this.api.post<Review>(`/review/reviews/assign/${detectionId}`);
    return response.data;
  }

  // Statistics endpoints
  async getReviewStats(days: number = 7): Promise<ReviewStats> {
    const response = await this.api.get<ReviewStats>('/review/stats/reviews', {
      params: { days }
    });
    return response.data;
  }

  async getDashboardStats(): Promise<DashboardStats> {
    const response = await this.api.get<DashboardStats>('/upload/stats/dashboard');
    return response.data;
  }

  async getReviewerWorkload(reviewerId: string): Promise<Record<string, number>> {
    const response = await this.api.get(`/review/stats/workload/${reviewerId}`);
    return response.data;
  }

  // Health check
  async healthCheck(): Promise<{ status: string }> {
    const response = await this.api.get('/review/health');
    return response.data;
  }

  // Generic API method for custom requests
  async request<T = any>(config: AxiosRequestConfig): Promise<AxiosResponse<T>> {
    return this.api.request<T>(config);
  }
}

// Export singleton instance
export const apiService = new ApiService();
export default apiService;