import { createSlice, createAsyncThunk, PayloadAction } from "@reduxjs/toolkit";
import { Notification, Recommendation } from "../../types";
import { recommendationsApi } from "../../api/client";

interface NotificationsState {
  notifications: Notification[];
  recommendations: Recommendation[];
  unreadCount: number;
  isLoading: boolean;
  error: string | null;
  lastFetched: string | null;
}

const initialState: NotificationsState = {
  notifications: [],
  recommendations: [],
  unreadCount: 0,
  isLoading: false,
  error: null,
  lastFetched: null,
};

// ─── Async Thunks ─────────────────────────────────────────────────────────────

export const fetchInbox = createAsyncThunk(
  "notifications/fetchInbox",
  async (
    { unreadOnly = false }: { unreadOnly?: boolean },
    { rejectWithValue }
  ) => {
    try {
      return await recommendationsApi.getInbox(unreadOnly);
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to fetch inbox");
    }
  }
);

export const fetchUnreadCount = createAsyncThunk(
  "notifications/fetchUnreadCount",
  async (_, { rejectWithValue }) => {
    try {
      return await recommendationsApi.getUnreadCount();
    } catch (error: any) {
      return rejectWithValue(0);
    }
  }
);

export const fetchRecommendations = createAsyncThunk(
  "notifications/fetchRecommendations",
  async (
    { limit = 20, offset = 0 }: { limit?: number; offset?: number },
    { rejectWithValue }
  ) => {
    try {
      return await recommendationsApi.getRecommendations(undefined, limit, offset);
    } catch (error: any) {
      return rejectWithValue(
        error.response?.data?.detail || "Failed to fetch recommendations"
      );
    }
  }
);

export const markNotificationRead = createAsyncThunk(
  "notifications/markRead",
  async (notificationId: number, { rejectWithValue }) => {
    try {
      await recommendationsApi.markNotificationRead(notificationId);
      return notificationId;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to mark as read");
    }
  }
);

export const acknowledgeRecommendation = createAsyncThunk(
  "notifications/acknowledge",
  async (recommendationId: number, { rejectWithValue }) => {
    try {
      await recommendationsApi.acknowledgeRecommendation(recommendationId);
      return recommendationId;
    } catch (error: any) {
      return rejectWithValue(
        error.response?.data?.detail || "Failed to acknowledge"
      );
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────────────────────

const notificationsSlice = createSlice({
  name: "notifications",
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
    addRealtimeNotification: (state, action: PayloadAction<Notification>) => {
      state.notifications.unshift(action.payload);
      state.unreadCount += 1;
    },
    decrementUnreadCount: (state) => {
      if (state.unreadCount > 0) {
        state.unreadCount -= 1;
      }
    },
    setUnreadCount: (state, action: PayloadAction<number>) => {
      state.unreadCount = action.payload;
    },
  },
  extraReducers: (builder) => {
    // Fetch inbox
    builder
      .addCase(fetchInbox.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchInbox.fulfilled, (state, action) => {
        state.isLoading = false;
        state.notifications = action.payload;
        state.unreadCount = action.payload.filter((n) => !n.is_read).length;
        state.lastFetched = new Date().toISOString();
      })
      .addCase(fetchInbox.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // Fetch unread count
    builder.addCase(fetchUnreadCount.fulfilled, (state, action) => {
      state.unreadCount = action.payload;
    });

    // Fetch recommendations
    builder
      .addCase(fetchRecommendations.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(fetchRecommendations.fulfilled, (state, action) => {
        state.isLoading = false;
        state.recommendations = action.payload;
      })
      .addCase(fetchRecommendations.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // Mark notification read
    builder.addCase(markNotificationRead.fulfilled, (state, action) => {
      const notification = state.notifications.find(
        (n) => n.id === action.payload
      );
      if (notification && !notification.is_read) {
        notification.is_read = true;
        notification.read_at = new Date().toISOString();
        if (state.unreadCount > 0) {
          state.unreadCount -= 1;
        }
      }
    });

    // Acknowledge recommendation
    builder.addCase(acknowledgeRecommendation.fulfilled, (state, action) => {
      state.recommendations = state.recommendations.filter(
        (r) => r.id !== action.payload
      );
      // Mark related notifications as read
      state.notifications.forEach((n) => {
        if (n.recommendation_id === action.payload && !n.is_read) {
          n.is_read = true;
          if (state.unreadCount > 0) {
            state.unreadCount -= 1;
          }
        }
      });
    });
  },
});

export const {
  clearError,
  addRealtimeNotification,
  decrementUnreadCount,
  setUnreadCount,
} = notificationsSlice.actions;
export default notificationsSlice.reducer;
