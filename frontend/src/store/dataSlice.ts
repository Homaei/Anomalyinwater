import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { 
  Image, 
  Detection, 
  Review, 
  ReviewWithDetails, 
  DetectionWithReview,
  PaginatedResponse,
  ReviewStats,
  DashboardStats
} from '@/types';
import apiService from '@/services/api';

interface DataState {
  // Images
  images: {
    items: Image[];
    total: number;
    currentPage: number;
    isLoading: boolean;
    error: string | null;
  };
  
  // Detections
  detections: {
    items: DetectionWithReview[];
    total: number;
    currentPage: number;
    isLoading: boolean;
    error: string | null;
  };
  
  // Reviews
  reviews: {
    items: ReviewWithDetails[];
    total: number;
    currentPage: number;
    isLoading: boolean;
    error: string | null;
  };
  
  // Pending reviews
  pendingReviews: {
    items: ReviewWithDetails[];
    isLoading: boolean;
    error: string | null;
  };
  
  // Statistics
  dashboardStats: {
    data: DashboardStats | null;
    isLoading: boolean;
    error: string | null;
  };
  
  reviewStats: {
    data: ReviewStats | null;
    isLoading: boolean;
    error: string | null;
  };
  
  // Currently selected items
  selectedImage: Image | null;
  selectedDetection: DetectionWithReview | null;
  selectedReview: ReviewWithDetails | null;
}

const initialState: DataState = {
  images: {
    items: [],
    total: 0,
    currentPage: 1,
    isLoading: false,
    error: null,
  },
  detections: {
    items: [],
    total: 0,
    currentPage: 1,
    isLoading: false,
    error: null,
  },
  reviews: {
    items: [],
    total: 0,
    currentPage: 1,
    isLoading: false,
    error: null,
  },
  pendingReviews: {
    items: [],
    isLoading: false,
    error: null,
  },
  dashboardStats: {
    data: null,
    isLoading: false,
    error: null,
  },
  reviewStats: {
    data: null,
    isLoading: false,
    error: null,
  },
  selectedImage: null,
  selectedDetection: null,
  selectedReview: null,
};

// Async thunks for images
export const fetchImages = createAsyncThunk(
  'data/fetchImages',
  async (params: { page?: number; size?: number; status?: string } = {}) => {
    const response = await apiService.getImages(params);
    return response;
  }
);

// Async thunks for detections
export const fetchDetections = createAsyncThunk(
  'data/fetchDetections',
  async (params: {
    page?: number;
    size?: number;
    is_anomaly?: boolean;
    min_confidence?: number;
    unreviewed_only?: boolean;
  } = {}) => {
    const response = await apiService.getDetections(params);
    return response;
  }
);

// Async thunks for reviews
export const fetchReviews = createAsyncThunk(
  'data/fetchReviews',
  async (params: {
    page?: number;
    size?: number;
    status?: string;
    reviewer_id?: string;
    sort_by?: string;
    sort_order?: string;
  } = {}) => {
    const response = await apiService.getReviews(params);
    return response;
  }
);

export const fetchPendingReviews = createAsyncThunk(
  'data/fetchPendingReviews',
  async (limit: number = 50) => {
    const response = await apiService.getPendingReviews(limit);
    return response;
  }
);

// Async thunks for statistics
export const fetchDashboardStats = createAsyncThunk(
  'data/fetchDashboardStats',
  async () => {
    const response = await apiService.getDashboardStats();
    return response;
  }
);

export const fetchReviewStats = createAsyncThunk(
  'data/fetchReviewStats',
  async (days: number = 7) => {
    const response = await apiService.getReviewStats(days);
    return response;
  }
);

// Async thunk for updating review
export const updateReview = createAsyncThunk(
  'data/updateReview',
  async ({ 
    reviewId, 
    data 
  }: { 
    reviewId: string; 
    data: {
      review_status?: string;
      human_verdict?: string;
      confidence_level?: number;
      notes?: string;
      review_duration_seconds?: number;
    }
  }) => {
    const response = await apiService.updateReview(reviewId, data);
    return response;
  }
);

const dataSlice = createSlice({
  name: 'data',
  initialState,
  reducers: {
    // Selection actions
    setSelectedImage: (state, action: PayloadAction<Image | null>) => {
      state.selectedImage = action.payload;
    },
    setSelectedDetection: (state, action: PayloadAction<DetectionWithReview | null>) => {
      state.selectedDetection = action.payload;
    },
    setSelectedReview: (state, action: PayloadAction<ReviewWithDetails | null>) => {
      state.selectedReview = action.payload;
    },
    
    // Clear errors
    clearImagesError: (state) => {
      state.images.error = null;
    },
    clearDetectionsError: (state) => {
      state.detections.error = null;
    },
    clearReviewsError: (state) => {
      state.reviews.error = null;
    },
    
    // Real-time updates
    addNewImage: (state, action: PayloadAction<Image>) => {
      state.images.items.unshift(action.payload);
      state.images.total += 1;
    },
    
    updateImageStatus: (state, action: PayloadAction<{ id: string; status: string }>) => {
      const image = state.images.items.find(img => img.id === action.payload.id);
      if (image) {
        image.processing_status = action.payload.status as any;
      }
    },
    
    addNewDetection: (state, action: PayloadAction<DetectionWithReview>) => {
      state.detections.items.unshift(action.payload);
      state.detections.total += 1;
      
      // Update dashboard stats if loaded
      if (state.dashboardStats.data) {
        state.dashboardStats.data.total_detections += 1;
        if (action.payload.is_anomaly) {
          state.dashboardStats.data.anomaly_count += 1;
        }
      }
    },
    
    updateReviewInList: (state, action: PayloadAction<Review>) => {
      const reviewIndex = state.reviews.items.findIndex(r => r.id === action.payload.id);
      if (reviewIndex >= 0) {
        state.reviews.items[reviewIndex] = {
          ...state.reviews.items[reviewIndex],
          ...action.payload
        };
      }
      
      // Remove from pending reviews if status changed
      if (action.payload.review_status !== 'pending') {
        state.pendingReviews.items = state.pendingReviews.items.filter(
          r => r.id !== action.payload.id
        );
      }
    },
  },
  extraReducers: (builder) => {
    // Images
    builder
      .addCase(fetchImages.pending, (state) => {
        state.images.isLoading = true;
        state.images.error = null;
      })
      .addCase(fetchImages.fulfilled, (state, action) => {
        state.images.isLoading = false;
        state.images.items = action.payload.items;
        state.images.total = action.payload.total;
        state.images.currentPage = action.payload.page;
      })
      .addCase(fetchImages.rejected, (state, action) => {
        state.images.isLoading = false;
        state.images.error = action.error.message || 'Failed to fetch images';
      });

    // Detections
    builder
      .addCase(fetchDetections.pending, (state) => {
        state.detections.isLoading = true;
        state.detections.error = null;
      })
      .addCase(fetchDetections.fulfilled, (state, action) => {
        state.detections.isLoading = false;
        state.detections.items = action.payload.items;
        state.detections.total = action.payload.total;
        state.detections.currentPage = action.payload.page;
      })
      .addCase(fetchDetections.rejected, (state, action) => {
        state.detections.isLoading = false;
        state.detections.error = action.error.message || 'Failed to fetch detections';
      });

    // Reviews
    builder
      .addCase(fetchReviews.pending, (state) => {
        state.reviews.isLoading = true;
        state.reviews.error = null;
      })
      .addCase(fetchReviews.fulfilled, (state, action) => {
        state.reviews.isLoading = false;
        state.reviews.items = action.payload.items;
        state.reviews.total = action.payload.total;
        state.reviews.currentPage = action.payload.page;
      })
      .addCase(fetchReviews.rejected, (state, action) => {
        state.reviews.isLoading = false;
        state.reviews.error = action.error.message || 'Failed to fetch reviews';
      });

    // Pending reviews
    builder
      .addCase(fetchPendingReviews.pending, (state) => {
        state.pendingReviews.isLoading = true;
        state.pendingReviews.error = null;
      })
      .addCase(fetchPendingReviews.fulfilled, (state, action) => {
        state.pendingReviews.isLoading = false;
        state.pendingReviews.items = action.payload;
      })
      .addCase(fetchPendingReviews.rejected, (state, action) => {
        state.pendingReviews.isLoading = false;
        state.pendingReviews.error = action.error.message || 'Failed to fetch pending reviews';
      });

    // Dashboard stats
    builder
      .addCase(fetchDashboardStats.pending, (state) => {
        state.dashboardStats.isLoading = true;
        state.dashboardStats.error = null;
      })
      .addCase(fetchDashboardStats.fulfilled, (state, action) => {
        state.dashboardStats.isLoading = false;
        state.dashboardStats.data = action.payload;
      })
      .addCase(fetchDashboardStats.rejected, (state, action) => {
        state.dashboardStats.isLoading = false;
        state.dashboardStats.error = action.error.message || 'Failed to fetch dashboard stats';
      });

    // Review stats
    builder
      .addCase(fetchReviewStats.pending, (state) => {
        state.reviewStats.isLoading = true;
        state.reviewStats.error = null;
      })
      .addCase(fetchReviewStats.fulfilled, (state, action) => {
        state.reviewStats.isLoading = false;
        state.reviewStats.data = action.payload;
      })
      .addCase(fetchReviewStats.rejected, (state, action) => {
        state.reviewStats.isLoading = false;
        state.reviewStats.error = action.error.message || 'Failed to fetch review stats';
      });

    // Update review
    builder
      .addCase(updateReview.fulfilled, (state, action) => {
        // Update review in the reviews list
        const reviewIndex = state.reviews.items.findIndex(r => r.id === action.payload.id);
        if (reviewIndex >= 0) {
          state.reviews.items[reviewIndex] = {
            ...state.reviews.items[reviewIndex],
            ...action.payload
          };
        }
        
        // Remove from pending reviews if no longer pending
        if (action.payload.review_status !== 'pending') {
          state.pendingReviews.items = state.pendingReviews.items.filter(
            r => r.id !== action.payload.id
          );
        }
      });
  },
});

export const {
  setSelectedImage,
  setSelectedDetection,
  setSelectedReview,
  clearImagesError,
  clearDetectionsError,
  clearReviewsError,
  addNewImage,
  updateImageStatus,
  addNewDetection,
  updateReviewInList,
} = dataSlice.actions;

export default dataSlice.reducer;