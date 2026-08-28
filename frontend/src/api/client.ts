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
  UniversePool,
  ScreenerStatus,
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
  createDemoAccount: async (label: string): Promise<{
    email: string;
    password: string;
    label: string;
    already_existed: boolean;
  }> => {
    const response = await api.post("/auth/demo-account", { label });
    return response.data;
  },

  listDemoAccounts: async (): Promise<Array<{
    id: number;
    email: string;
    label: string;
    is_active: boolean;
    created_at: string;
  }>> => {
    const response = await api.get("/auth/demo-accounts");
    return response.data;
  },

  revokeDemoAccount: async (id: number): Promise<any> => {
    const response = await api.post(`/auth/demo-accounts/${id}/revoke`);
    return response.data;
  },

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

  login: async (email: string, password: string): Promise<AuthResponse | { requires_2fa: true; pre_auth_token: string }> => {
    const response = await api.post("/auth/login", { email, password });
    if (response.data.requires_2fa) return response.data;
    const { tokens } = response.data as AuthResponse;
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    return response.data as AuthResponse;
  },

  complete2FALogin: async (preAuthToken: string, code: string): Promise<AuthResponse> => {
    const response = await api.post<AuthResponse>("/auth/2fa/login", null, {
      params: { pre_auth_token: preAuthToken, code },
    });
    const { tokens } = response.data;
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    return response.data;
  },

  setup2FA: async (): Promise<{ secret: string; otp_uri: string; qr_code: string }> => {
    const response = await api.post("/auth/2fa/setup");
    return response.data;
  },

  enable2FA: async (code: string): Promise<void> => {
    await api.post("/auth/2fa/enable", null, { params: { code } });
  },

  disable2FA: async (code: string): Promise<void> => {
    await api.post("/auth/2fa/disable", null, { params: { code } });
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

  telegramLinkCode: async (): Promise<{ link: string; expires_in: number }> => {
    const response = await api.post("/auth/telegram/link-code");
    return response.data;
  },

  telegramStatus: async (): Promise<{ linked: boolean }> => {
    const response = await api.get("/auth/telegram/status");
    return response.data;
  },

  telegramUnlink: async (): Promise<{ linked: boolean }> => {
    const response = await api.delete("/auth/telegram/link");
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

  removePosition: async (symbol: string): Promise<{ removed: boolean; symbol: string }> => {
    const response = await api.delete(`/portfolio/${symbol}`);
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
    limit = 200,
    offset = 0
  ): Promise<Recommendation[]> => {
    const response = await api.get<Recommendation[]>("/recommendations/", {
      params: { status_filter: statusFilter, limit, offset },
    });
    return response.data;
  },

  getInbox: async (
    unreadOnly = false,
    limit = 50,
    offset = 0,
    notificationType?: string,
  ): Promise<Notification[]> => {
    const response = await api.get<Notification[]>("/recommendations/inbox", {
      params: {
        unread_only: unreadOnly,
        limit,
        offset,
        ...(notificationType ? { notification_type: notificationType } : {}),
      },
    });
    return response.data;
  },

  getHiddenCount: async (): Promise<{
    hidden_total: number;
    hidden_short: number;
    hidden_volatile: number;
  }> => {
    const response = await api.get("/recommendations/hidden-count");
    return response.data;
  },

  deleteNotification: async (notificationId: number): Promise<void> => {
    await api.delete(`/recommendations/inbox/${notificationId}`);
  },

  clearReadNotifications: async (): Promise<number> => {
    const response = await api.delete<{ deleted: number }>("/recommendations/inbox");
    return response.data.deleted;
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

  getScanActivity: async (days = 7): Promise<{
    days: number;
    total: number;
    shown: number;
    counts: Record<string, number>;
    confidence_stats: {
      count: number;
      min: number;
      max: number;
      median: number;
      mean: number;
      spread: number;
      stdev: number;
      buckets: Record<string, number>;
    } | null;
    items: Array<{
      id: number;
      symbol: string;
      recommendation_type: string;
      status: string;
      bucket: string;
      abort_reason: string | null;
      confidence_score: number;
      created_at: string | null;
      reason: string;
      trigger_type: string | null;
    }>;
  }> => {
    const response = await api.get("/recommendations/scan-activity", { params: { days } });
    return response.data;
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

  // Every stock in the scan pool with whatever analysis it already has.
  getUniversePool: async (): Promise<UniversePool> => {
    const response = await api.get<UniversePool>("/market/universe/pool");
    return response.data;
  },

  runScreener: async (): Promise<any> => {
    const response = await api.post("/market/universe/screen");
    return response.data;
  },

  getScreenerStatus: async (): Promise<ScreenerStatus> => {
    const response = await api.get<ScreenerStatus>("/market/universe/screen-status");
    return response.data;
  },

  loadUniverse: async (): Promise<any> => {
    const response = await api.post("/market/universe/load");
    return response.data;
  },

  scanPoolNow: async (): Promise<any> => {
    const response = await api.post("/market/pool/scan-now");
    return response.data;
  },

  getScanStatus: async (): Promise<any> => {
    const response = await api.get("/market/pool/scan-status");
    return response.data;
  },

  getEarningsStatus: async (): Promise<any> => {
    const response = await api.get("/market/earnings/status");
    return response.data;
  },

  checkEarningsNow: async (): Promise<any> => {
    const response = await api.post("/market/earnings/check-now");
    return response.data;
  },

  resetEarnings: async (): Promise<any> => {
    const response = await api.post("/market/earnings/reset");
    return response.data;
  },

  simulateTaScan: async (): Promise<any> => {
    const response = await api.post("/market/simulate/ta-scan-now");
    return response.data;
  },

  runQuarterlyBatch: async (): Promise<any> => {
    const response = await api.post("/market/quarterly/run-batch");
    return response.data;
  },

  retireStaleRecommendations: async (): Promise<any> => {
    const response = await api.post("/market/recommendations/retire-stale");
    return response.data;
  },

  getQuarterlyStatus: async (): Promise<{
    active: boolean;
    quarter: string;
    total: number;
    done: number;
    remaining: number;
    progress_pct: number;
    batch_running: boolean;
  }> => {
    const response = await api.get("/market/quarterly/status");
    return response.data;
  },

  requeueReporters: async (): Promise<any> => {
    const response = await api.post("/market/quarterly/requeue-reporters");
    return response.data;
  },

  backfillBeta: async (): Promise<any> => {
    const response = await api.post("/market/universe/backfill-beta");
    return response.data;
  },

  getBackfillBetaStatus: async (): Promise<{
    running: boolean;
    done?: number;
    total?: number;
  }> => {
    const response = await api.get("/market/universe/backfill-beta/status");
    return response.data;
  },

  simulateTestNotification: async (): Promise<any> => {
    const response = await api.post("/market/simulate/test-notification");
    return response.data;
  },

  simulateTestAdminAlert: async (): Promise<any> => {
    const response = await api.post("/market/simulate/test-admin-alert");
    return response.data;
  },

  // Full real one-stock analysis to verify all 3 AI engines fire (1-3 min).
  // Runs in the background on the server and polls for the result, so it
  // survives mobile connections that can't hold a long request open.
  simulateAiEnginesCheck: async (symbol: string): Promise<any> => {
    await api.post("/market/simulate/ai-engines-check", null, { params: { symbol } });
    const deadline = Date.now() + 5 * 60 * 1000; // 5-min safety cap
    // small helper — avoids pulling in extra deps
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
    while (Date.now() < deadline) {
      await wait(5000);
      const { data } = await api.get("/market/simulate/ai-engines-status");
      if (data && data.running === false) return data;
    }
    throw new Error("AI engines check timed out (still running after 5 min)");
  },

  // Downloads a full data backup (one CSV per table, zipped). Railway keeps
  // volume backups behind the Pro plan, so this is the actual safety net.
  downloadBackup: async (): Promise<any> => {
    const response = await api.get("/backup/export", { responseType: "blob" });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const a = document.createElement("a");
    a.href = url;
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "");
    a.download = `investment-ai-backup-${stamp}.zip`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    const mb = (response.data.size / (1024 * 1024)).toFixed(2);
    return { downloaded: true, size_mb: mb };
  },

  getBackupStatus: async (): Promise<any> => {
    const response = await api.get("/backup/status");
    return response.data;
  },

  // What every earnings calendar says about one symbol, plus the verdict the
  // watcher reaches — explains a row that looks stuck.
  checkEarningsForSymbol: async (symbol: string): Promise<any> => {
    const response = await api.get(`/market/diagnostics/earnings/${symbol}`);
    return response.data;
  },

  // Probes each price provider individually — free, no AI, answers "is it one
  // provider blocking us or are we down to nothing?"
  checkPriceSources: async (symbol: string): Promise<any> => {
    const response = await api.get("/market/diagnostics/price-sources", {
      params: { symbol },
    });
    return response.data;
  },

  simulateCreatePosition: async (symbol: string, quantity = 10, price = 100): Promise<any> => {
    const response = await api.post("/market/simulate/create-test-position", null, {
      params: { symbol, quantity, price },
    });
    return response.data;
  },

  simulateRemovePosition: async (symbol: string): Promise<any> => {
    const response = await api.delete("/market/simulate/remove-test-position", {
      params: { symbol },
    });
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

  setPriceAlert: async (
    id: number,
    alertPriceAbove?: number | null,
    alertPriceBelow?: number | null
  ): Promise<void> => {
    await api.put(`/watchlist/${id}/alert`, {
      alert_price_above: alertPriceAbove ?? null,
      alert_price_below: alertPriceBelow ?? null,
    });
  },
};

// ─── Performance API ──────────────────────────────────────────────────────────

export const performanceApi = {
  getSummary: async (): Promise<any> => {
    const response = await api.get("/performance/summary");
    return response.data;
  },

  getHistory: async (limit = 50, outcomeOnly = false): Promise<any[]> => {
    const response = await api.get("/performance/history", {
      params: { limit, outcome_only: outcomeOnly },
    });
    return response.data;
  },

  getComparison: async (): Promise<any> => {
    const response = await api.get("/performance/comparison");
    return response.data;
  },

  getTimeline: async (): Promise<any[]> => {
    const response = await api.get("/performance/timeline");
    return response.data;
  },

  getPortfolioHistory: async (days = 90): Promise<any[]> => {
    const response = await api.get("/performance/portfolio-history", {
      params: { days },
    });
    return response.data;
  },

  snapshotNow: async (): Promise<any> => {
    const response = await api.post("/performance/snapshot-now");
    return response.data;
  },

  trackNow: async (): Promise<any> => {
    const response = await api.post("/performance/track-now");
    return response.data;
  },

  getBacktest: async (initialCapital = 100000): Promise<any> => {
    const response = await api.get("/performance/backtest", {
      params: { initial_capital: initialCapital },
    });
    return response.data;
  },
};

// ─── Enhanced Market API additions ───────────────────────────────────────────

export const marketExtApi = {
  getEarningsCalendar: async (symbols?: string, daysAhead = 14): Promise<any[]> => {
    const response = await api.get("/market/earnings-calendar", {
      params: { symbols, days_ahead: daysAhead },
    });
    return response.data;
  },

  getSectors: async (): Promise<any> => {
    const response = await api.get("/market/sectors");
    return response.data;
  },

  compareStocks: async (symbols: string[], exchange = "NASDAQ"): Promise<any> => {
    const response = await api.post("/market/compare", { symbols, exchange });
    return response.data;
  },

  getInsiderActivity: async (symbol: string): Promise<any> => {
    const response = await api.get(`/market/insider/${symbol}`);
    return response.data;
  },

  getSecFilings: async (symbol: string): Promise<any> => {
    const response = await api.get(`/market/sec-filings/${symbol}`);
    return response.data;
  },
};

export default api;
