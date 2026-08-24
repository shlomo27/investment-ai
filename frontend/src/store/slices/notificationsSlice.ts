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
  hasMoreInbox: boolean;
}

const initialState: NotificationsState = {
  notifications: [],
  recommendations: [],
  unreadCount: 0,
  isLoading: false,
  error: null,
  lastFetched: null,
  hasMoreInbox: false,
};

// ─── Async Thunks ─────────────────────────────────────────────────────────────

export const INBOX_PAGE_SIZE = 50;

export const fetchInbox = createAsyncThunk(
  "notifications/fetchInbox",
  async (
    {
      unreadOnly = false,
      offset = 0,
      notificationType,
    }: { unreadOnly?: boolean; offset?: number; notificationType?: string },
    { rejectWithValue }
  ) => {
    try {
      const items = await recommendationsApi.getInbox(
        unreadOnly, INBOX_PAGE_SIZE, offset, notificationType,
      );
      // A short page means the end — no total is needed to know when to stop.
      return { items, offset, hasMore: items.length === INBOX_PAGE_SIZE };
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
    // Drop rows locally after the server confirms the delete, so the list does
    // not jump back on the next render while a refetch is in flight.
    removeNotification: (state, action: PayloadAction<number>) => {
      const gone = state.notifications.find((n) => n.id === action.payload);
      state.notifications = state.notifications.filter((n) => n.id !== action.payload);
      if (gone && !gone.is_read && state.unreadCount > 0) state.unreadCount -= 1;
    },
    removeReadNotifications: (state) => {
      state.notifications = state.notifications.filter((n) => !n.is_read);
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
        const { items, offset, hasMore } = action.payload;
        // offset 0 is a fresh load or a filter change; anything else appends.
        state.notifications = offset === 0 ? items : [...state.notifications, ...items];
        state.hasMoreInbox = hasMore;
        if (offset === 0) {
          state.unreadCount = items.filter((n) => !n.is_read).length;
        }
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
  removeNotification,
  removeReadNotifications,
  addRealtimeNotification,
  decrementUnreadCount,
  setUnreadCount,
} = notificationsSlice.actions;
export default notificationsSlice.reducer;
