import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from "axios";
import {
  AuthResponse,
  User,
  Token,
  PortfolioPosition,
  PortfolioSummary,
  Order,
  OrderType,
  Recommendation,
  Notification,
  WatchlistItem,
  RiskMetrics,
  RebalancingSuggestion,
  ExposureCheck,
  Asset,
  RiskProfile,
  TechnicalAnalysis,
  UniverseStats,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL || "";

// ─── Axios Instance ──────────────────────────────────────────────────────────

const api: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

// ─── Request Interceptor: Attach JWT Token ───────────────────────────────────

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response Interceptor: Handle Token Refresh ──────────────────────────────

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value: any) => void;
  reject: (reason?: any) => void;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as AxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers!["Authorization"] = `Bearer ${token}`;
            return api(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem("refresh_token");
      if (!refreshToken) {
        localStorage.clear();
        window.location.href = "/login";
        return Promise.reject(error);
      }

      try {
        const response = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token, refresh_token } = response.data;
        localStorage.setItem("access_token", access_token);
        localStorage.setItem("refresh_token", refresh_token);

        api.defaults.headers.common["Authorization"] = `Bearer ${access_token}`;
        processQueue(null, access_token);
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        localStorage.clear();
        window.location.href = "/login";
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ─── Auth API ────────────────────────────────────────────────────────────────

export const authApi = {
  register: async (data: {
    email: string;
    password: string;
    full_name: string;
    phone?: string;
    preferred_language?: string;
  }): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>("/auth/register", data);
    const { tokens } = response.data;
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    return response.data;
  },

  login: async (email: string, password: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>("/auth/login", {
      email,
      password,
    });
    const { tokens } = response.data;
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    return response.data;
  },

  logout: async (): Promise<void> => {
    try {
      await api.post("/auth/logout");
    } finally {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
    }
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>("/auth/me");
    return response.data;
  },

  updateProfile: async (data: Partial<User> & { push_token?: string }): Promise<User> => {
    const response = await api.put<User>("/auth/profile", data);
    return response.data;
  },

  completeOnboarding: async (data: {
    risk_profile: RiskProfile;
    risk_score: number;
    investment_type: string;
    allows_volatile: boolean;
    allows_leveraged: boolean;
    allows_short: boolean;
    notification_email: boolean;
    notification_sms: boolean;
    notification_push: boolean;
  }): Promise<User> => {
    const response = await api.post<User>("/auth/onboarding", data);
    return response.data;
  },
};

// ─── Portfolio API ────────────────────────────────────────────────────────────

export const portfolioApi = {
  getPortfolio: async (): Promise<PortfolioPosition[]> => {
    const response = await api.get<PortfolioPosition[]>("/portfolio/");
    return response.data;
  },

  getSummary: async (): Promise<PortfolioSummary> => {
    const response = await api.get<PortfolioSummary>("/portfolio/summary");
    return response.data;
  },

  getRisk: async (): Promise<RiskMetrics> => {
    const response = await api.get<RiskMetrics>("/portfolio/risk");
    return response.data;
  },

  getRebalancingSuggestions: async (): Promise<RebalancingSuggestion[]> => {
    const response = await api.get<RebalancingSuggestion[]>("/portfolio/rebalancing");
    return response.data;
  },

  updateSettings: async (maxExposurePct: number): Promise<void> => {
    await api.post("/portfolio/settings", {
      max_single_asset_exposure_pct: maxExposurePct,
    });
  },

  getAssetPosition: async (symbol: string): Promise<PortfolioPosition> => {
    const response = await api.get<PortfolioPosition>(`/portfolio/${symbol}`);
    return response.data;
  },
};

// ─── Orders API ──────────────────────────────────────────────────────────────

export const ordersApi = {
  createOrder: async (data: {
    symbol: string;
    order_type: OrderType;
    quantity: number;
    price: number;
    recommendation_id?: number;
    notes?: string;
  }): Promise<Order> => {
    const response = await api.post<Order>("/orders/", data);
    return response.data;
  },

  getOrders: async (
    statusFilter?: string,
    limit = 50,
    offset = 0
  ): Promise<Order[]> => {
    const response = await api.get<Order[]>("/orders/", {
      params: { status_filter: statusFilter, limit, offset },
    });
    return response.data;
  },

  getOrder: async (orderId: number): Promise<Order> => {
    const response = await api.get<Order>(`/orders/${orderId}`);
    return response.data;
  },

  cancelOrder: async (orderId: number): Promise<void> => {
    await api.delete(`/orders/${orderId}`);
  },

  confirmOrder: async (orderId: number): Promise<Order> => {
    const response = await api.post<Order>(`/orders/${orderId}/confirm`);
    return response.data;
  },

  checkExposure: async (symbol: string, amount: number): Promise<ExposureCheck> => {
    const response = await api.get<ExposureCheck>("/orders/exposure-check", {
      params: { symbol, amount },
    });
    return response.data;
  },
};

// ─── Recommendations API ─────────────────────────────────────────────────────

export const recommendationsApi = {
  getRecommendations: async (
    statusFilter?: string,
    limit = 20,
    offset = 0
  ): Promise<Recommendation[]> => {
    const response = await api.get<Recommendation[]>("/recommendations/", {
      params: { status_filter: statusFilter, limit, offset },
    });
    return response.data;
  },

  getInbox: async (unreadOnly = false, limit = 50): Promise<Notification[]> => {
    const response = await api.get<Notification[]>("/recommendations/inbox", {
      params: { unread_only: unreadOnly, limit },
    });
    return response.data;
  },

  getUnreadCount: async (): Promise<number> => {
    const response = await api.get<{ unread_count: number }>(
      "/recommendations/unread-count"
    );
    return response.data.unread_count;
  },

  getRecommendation: async (id: number): Promise<Recommendation> => {
    const response = await api.get<Recommendation>(`/recommendations/${id}`);
    return response.data;
  },

  acknowledgeRecommendation: async (id: number): Promise<void> => {
    await api.post(`/recommendations/${id}/acknowledge`);
  },

  markNotificationRead: async (notificationId: number): Promise<void> => {
    await api.post(`/recommendations/inbox/${notificationId}/read`);
  },

  requestTechnicalAnalysis: async (
    recommendationId: number
  ): Promise<{ technical_analysis: TechnicalAnalysis }> => {
    const response = await api.post<{ technical_analysis: TechnicalAnalysis }>(
      `/recommendations/${recommendationId}/request-technical`
    );
    return response.data;
  },

  recomputeQuantModels: async (
    recommendationId: number
  ): Promise<{ quantitative_models: any }> => {
    const response = await api.post<{ quantitative_models: any }>(
      `/recommendations/${recommendationId}/recompute-quant-models`
    );
    return response.data;
  },
};

// ─── Market API ──────────────────────────────────────────────────────────────

export const marketApi = {
  search: async (query: string, exchange?: string): Promise<any[]> => {
    const response = await api.get<any[]>("/market/search", {
      params: { q: query, exchange },
    });
    return response.data;
  },

  searchTASE: async (query: string): Promise<any[]> => {
    const response = await api.get<any[]>("/market/tase/search", {
      params: { q: query },
    });
    return response.data;
  },

  getAssetPool: async (params?: {
    activeOnly?: boolean;
    exchange?: string;
    riskLevel?: string;
    sector?: string;
  }): Promise<Asset[]> => {
    const response = await api.get<Asset[]>("/market/pool", {
      params: {
        active_only: params?.activeOnly ?? true,
        exchange: params?.exchange,
        risk_level: params?.riskLevel,
        sector: params?.sector,
      },
    });
    return response.data;
  },

  getAssetData: async (
    symbol: string,
    includeTechnical = false
  ): Promise<any> => {
    const response = await api.get(`/market/asset/${symbol}`, {
      params: { include_technical: includeTechnical },
    });
    return response.data;
  },

  addToPool: async (symbol: string, exchange: string): Promise<void> => {
    await api.post("/market/pool/add", null, {
      params: { symbol, exchange },
    });
  },

  getUniverseStats: async (): Promise<UniverseStats> => {
    const response = await api.get<UniverseStats>("/market/universe/stats");
    return response.data;
  },

  runScreener: async (): Promise<any> => {
    const response = await api.post("/market/universe/screen");
    return response.data;
  },

  loadUniverse: async (): Promise<any> => {
    const response = await api.post("/market/universe/load");
    return response.data;
  },

  scanPoolNow: async (batch = 30): Promise<any> => {
    const response = await api.post("/market/pool/scan-now", null, { params: { batch } });
    return response.data;
  },
};

// ─── Watchlist API ────────────────────────────────────────────────────────────

export const watchlistApi = {
  getWatchlist: async (): Promise<WatchlistItem[]> => {
    const response = await api.get<WatchlistItem[]>("/watchlist/");
    return response.data;
  },

  addToWatchlist: async (data: {
    symbol: string;
    exchange?: string;
    alert_on_technical_signal?: boolean;
    notes?: string;
  }): Promise<WatchlistItem> => {
    const response = await api.post<WatchlistItem>("/watchlist/", data);
    return response.data;
  },

  removeFromWatchlist: async (id: number): Promise<void> => {
    await api.delete(`/watchlist/${id}`);
  },

  runTechnicalAnalysis: async (
    id: number
  ): Promise<{ technical_analysis: TechnicalAnalysis; workflow_status: string }> => {
    const response = await api.post(`/watchlist/${id}/technical-analysis`);
    return response.data;
  },

  updateSettings: async (
    id: number,
    alertOnSignal: boolean,
    notes?: string
  ): Promise<void> => {
    await api.put(`/watchlist/${id}/settings`, null, {
      params: { alert_on_technical_signal: alertOnSignal, notes },
    });
  },
};

export default api;
