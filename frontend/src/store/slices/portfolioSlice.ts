import { createSlice, createAsyncThunk, PayloadAction } from "@reduxjs/toolkit";
import {
  PortfolioPosition,
  PortfolioSummary,
  RiskMetrics,
  RebalancingSuggestion,
} from "../../types";
import { portfolioApi } from "../../api/client";

interface PortfolioState {
  positions: PortfolioPosition[];
  summary: PortfolioSummary | null;
  risk: RiskMetrics | null;
  rebalancingSuggestions: RebalancingSuggestion[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: string | null;
}

const initialState: PortfolioState = {
  positions: [],
  summary: null,
  risk: null,
  rebalancingSuggestions: [],
  isLoading: false,
  error: null,
  lastUpdated: null,
};

// ─── Async Thunks ─────────────────────────────────────────────────────────────

export const fetchPortfolio = createAsyncThunk(
  "portfolio/fetchAll",
  async (_, { rejectWithValue }) => {
    try {
      return await portfolioApi.getPortfolio();
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to fetch portfolio");
    }
  }
);

export const fetchPortfolioSummary = createAsyncThunk(
  "portfolio/fetchSummary",
  async (_, { rejectWithValue }) => {
    try {
      return await portfolioApi.getSummary();
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to fetch summary");
    }
  }
);

export const fetchPortfolioRisk = createAsyncThunk(
  "portfolio/fetchRisk",
  async (_, { rejectWithValue }) => {
    try {
      return await portfolioApi.getRisk();
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to fetch risk");
    }
  }
);

export const fetchRebalancingSuggestions = createAsyncThunk(
  "portfolio/fetchRebalancing",
  async (_, { rejectWithValue }) => {
    try {
      return await portfolioApi.getRebalancingSuggestions();
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to fetch suggestions");
    }
  }
);

export const updatePortfolioSettings = createAsyncThunk(
  "portfolio/updateSettings",
  async (maxExposurePct: number, { rejectWithValue }) => {
    try {
      await portfolioApi.updateSettings(maxExposurePct);
      return maxExposurePct;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || "Failed to update settings");
    }
  }
);

// ─── Slice ────────────────────────────────────────────────────────────────────

const portfolioSlice = createSlice({
  name: "portfolio",
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
    updatePositionPrice: (
      state,
      action: PayloadAction<{ symbol: string; price: number }>
    ) => {
      const position = state.positions.find(
        (p) => p.symbol === action.payload.symbol
      );
      if (position) {
        position.current_price = action.payload.price;
        position.current_value = position.quantity * action.payload.price;
        position.pnl =
          position.current_value -
          position.quantity * position.avg_buy_price;
        position.pnl_percentage =
          position.avg_buy_price > 0
            ? ((position.current_price - position.avg_buy_price) /
                position.avg_buy_price) *
              100
            : 0;
      }
    },
  },
  extraReducers: (builder) => {
    // Fetch portfolio
    builder
      .addCase(fetchPortfolio.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchPortfolio.fulfilled, (state, action) => {
        state.isLoading = false;
        state.positions = action.payload;
        state.lastUpdated = new Date().toISOString();
      })
      .addCase(fetchPortfolio.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // Fetch summary
    builder
      .addCase(fetchPortfolioSummary.pending, (state) => {
        state.isLoading = true;
      })
      .addCase(fetchPortfolioSummary.fulfilled, (state, action) => {
        state.isLoading = false;
        state.summary = action.payload;
        state.positions = action.payload.positions;
        state.lastUpdated = new Date().toISOString();
      })
      .addCase(fetchPortfolioSummary.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // Fetch risk
    builder
      .addCase(fetchPortfolioRisk.fulfilled, (state, action) => {
        state.risk = action.payload;
      });

    // Fetch rebalancing
    builder
      .addCase(fetchRebalancingSuggestions.fulfilled, (state, action) => {
        state.rebalancingSuggestions = action.payload;
      });
  },
});

export const { clearError, updatePositionPrice } = portfolioSlice.actions;
export default portfolioSlice.reducer;
