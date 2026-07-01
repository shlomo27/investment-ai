// ─── Enums ─────────────────────────────────────────────────────────────────

export enum RiskProfile {
  CONSERVATIVE = "CONSERVATIVE",
  PASSIVE = "PASSIVE",
  AGGRESSIVE = "AGGRESSIVE",
  HYBRID = "HYBRID",
}

export enum OrderType {
  BUY = "BUY",
  SELL = "SELL",
}

export enum OrderStatus {
  PENDING = "PENDING",
  EXECUTED = "EXECUTED",
  CANCELLED = "CANCELLED",
  REJECTED = "REJECTED",
  PARTIALLY_FILLED = "PARTIALLY_FILLED",
}

export enum RecommendationType {
  BUY = "BUY",
  SELL = "SELL",
  HOLD = "HOLD",
  STRONG_BUY = "STRONG_BUY",
  STRONG_SELL = "STRONG_SELL",
}

export enum RecommendationStatus {
  PENDING_SENIOR_REVIEW = "PENDING_SENIOR_REVIEW",
  APPROVED = "APPROVED",
  REJECTED = "REJECTED",
  PRESENTED_TO_USER = "PRESENTED_TO_USER",
  ACTIONED = "ACTIONED",
  DISMISSED = "DISMISSED",
}

export enum NotificationType {
  RECOMMENDATION = "RECOMMENDATION",
  ALERT = "ALERT",
  SYSTEM = "SYSTEM",
  RISK_WARNING = "RISK_WARNING",
  PRICE_TARGET = "PRICE_TARGET",
}

export enum Exchange {
  NASDAQ = "NASDAQ",
  NYSE = "NYSE",
  TASE = "TASE",
  AMEX = "AMEX",
  LSE = "LSE",
  EURONEXT = "EURONEXT",
  OTHER = "OTHER",
}

export enum RiskLevel {
  LOW = "LOW",
  MEDIUM = "MEDIUM",
  HIGH = "HIGH",
  VERY_HIGH = "VERY_HIGH",
}

export enum AssetType {
  STOCK = "STOCK",
  ETF = "ETF",
  BOND = "BOND",
  CRYPTO = "CRYPTO",
  COMMODITY = "COMMODITY",
}

export enum TechnicalSignal {
  STRONG_BUY = "STRONG_BUY",
  BUY_NOW = "BUY_NOW",
  WAIT = "WAIT",
  SELL_NOW = "SELL_NOW",
  STRONG_SELL = "STRONG_SELL",
}

// ─── Core Models ────────────────────────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone?: string;
  risk_profile: RiskProfile;
  risk_score: number;
  age_group?: string;
  investment_horizon_months?: number;
  allows_short?: boolean;
  allows_volatile?: boolean;
  cash_balance: number;
  max_single_asset_exposure: number;
  is_active: boolean;
  is_admin: boolean;
  is_onboarded: boolean;
  preferred_language: "he" | "en";
  notification_email: boolean;
  notification_sms: boolean;
  notification_push: boolean;
  totp_enabled: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AuthResponse {
  user: User;
  tokens: Token;
}

export interface PortfolioPosition {
  id: number;
  symbol: string;
  quantity: number;
  avg_buy_price: number;
  current_price: number;
  current_value: number;
  pnl: number;
  pnl_percentage: number;
  exposure_percentage: number;
  asset_name?: string;
  sector?: string;
  risk_level?: RiskLevel;
  updated_at: string;
}

export interface PortfolioSummary {
  total_value: number;
  cash_balance: number;
  total_market_value: number;
  total_cost_basis: number;
  total_pnl: number;
  total_pnl_pct: number;
  position_count: number;
  risk_score?: number;
  risk_level?: string;
  positions: PortfolioPosition[];
}

export interface Asset {
  id: number;
  symbol: string;
  name: string;
  exchange: Exchange;
  asset_type: AssetType;
  risk_level: RiskLevel;
  sector?: string;
  country: string;
  last_price?: number;
  market_cap?: number;
  pe_ratio?: number;
  sentiment_score: number;
  fundamental_score: number;
  is_active_in_pool: boolean;
}

export interface Order {
  id: number;
  symbol: string;
  order_type: OrderType;
  status: OrderStatus;
  quantity: number;
  price_at_order: number;
  executed_price?: number;
  total_amount: number;
  executed_total?: number;
  notes?: string;
  rejection_reason?: string;
  created_at: string;
  executed_at?: string;
  cancelled_at?: string;
}

export interface QuantDCFYear {
  year: number;
  fcf_mm: number;
  pv_factor: number;
  pv_mm: number;
}

export interface QuantDCF {
  intrinsic_value?: number;
  current_price?: number;
  upside_pct?: number;
  wacc_pct?: number;
  fcf_growth_pct?: number;
  terminal_growth_pct?: number;
  pv_5yr_fcf?: number;
  pv_terminal?: number;
  terminal_value_total?: number;
  total_equity?: number;
  fcf_base_mm?: number;
  shares_mm?: number;
  yearly_projections?: QuantDCFYear[];
  skipped?: string;
  error?: string;
}

export interface QuantDDM {
  intrinsic_value?: number;
  current_price?: number;
  upside_pct?: number;
  dividend_per_share?: number;
  growth_rate_pct?: number;
  cost_of_equity_pct?: number;
  skipped?: string;
  error?: string;
}

export interface QuantSensitivity {
  current_eps?: number;
  current_pe?: number;
  current_price?: number;
  pe_scenarios?: number[];
  growth_scenarios?: string[];
  table?: Record<string, Record<string, number>>;
  skipped?: string;
  error?: string;
}

export interface QuantMonteCarlo {
  current_price?: number;
  p10?: number;
  p25?: number;
  mean?: number;
  p75?: number;
  p90?: number;
  prob_above_pct?: number;
  annual_vol_pct?: number;
  annual_drift_pct?: number;
  simulations?: number;
  horizon_days?: number;
  skipped?: string;
  error?: string;
}

export interface QuantCompsMultiple {
  company: number;
  sector_avg: number;
  premium_pct: number;
  implied_price: number;
  upside_pct: number;
}

export interface QuantComps {
  sector?: string;
  matched_key?: string;
  sector_averages?: Record<string, number>;
  comparisons?: {
    pe?: QuantCompsMultiple;
    pb?: QuantCompsMultiple;
    ps?: QuantCompsMultiple;
  };
  error?: string;
}

export interface QuantitativeModels {
  dcf?: QuantDCF;
  ddm?: QuantDDM;
  sensitivity?: QuantSensitivity;
  monte_carlo?: QuantMonteCarlo;
  comps?: QuantComps;
}

export interface CatalystValidation {
  primary_catalyst?: string;
  is_specific?: boolean;
  is_dated?: boolean;
  expected_date?: string;
  is_quantified?: boolean;
  quantified_impact?: string;
  is_verifiable?: boolean;
  not_priced_in?: boolean;
  catalyst_score?: number;
}

export interface ScenarioLeg {
  probability_pct: number;
  trigger?: string;
  price_target?: number;
  timeline_months?: number;
  upside_pct?: number;
  downside_pct?: number;
}

export interface ScenarioAnalysis {
  bull?: ScenarioLeg;
  base?: ScenarioLeg;
  bear?: ScenarioLeg;
}

export interface ThesisBreaker {
  rank: number;
  risk: string;
  probability_pct: number;
  impact_pct: number;
  risk_adjusted_cost_pct: number;
}

export interface FundamentalAnalysis {
  recommendation_type: RecommendationType;
  direction_bias?: "LONG" | "SHORT" | "NEUTRAL";
  confidence_score: number;
  valuation_assessment: "UNDERVALUED" | "FAIRLY_VALUED" | "OVERVALUED";
  financial_health: "EXCELLENT" | "GOOD" | "FAIR" | "POOR";
  key_metrics_summary: {
    pe_assessment?: string;
    growth_quality?: string;
    balance_sheet_strength?: string;
    cash_flow_quality?: string;
    sentiment_alignment?: string;
  };
  thesis?: string;
  bull_case: string;
  bear_case: string;
  short_catalysts?: string[];
  risk_factors: string[];
  catalysts: string[];
  investment_horizon: "SHORT_TERM" | "MEDIUM_TERM" | "LONG_TERM";
  sector_comparison: string;
  sentiment_cross_check: string;
  analyst_notes: string;
  expected_return_pct?: number;
  quantitative_models?: QuantitativeModels;
  // Deep-dive fields emitted by the fundamental agent (optional; may be absent on older records)
  data_completeness?: number;
  hard_exclusions_triggered?: string[];
  auto_disqualified?: boolean;
  moat_classification?: "COST_MONOPOLY" | "SWITCHING_COST" | "NETWORK_EFFECT" | "REGULATORY" | "NONE";
  moat_evidence?: string;
  catalyst_validation?: CatalystValidation;
  scenario_analysis?: ScenarioAnalysis;
  expected_value?: number | null;
  expected_value_vs_current_pct?: number | null;
  allocation_recommendation?: "HIGH" | "MEDIUM" | "LOW" | "HOLD" | "NONE";
  suggested_weight_range?: string;
  thesis_breakers?: ThesisBreaker[];
}

export interface SentimentData {
  score: number;
  mentions: number;
  trending: boolean;
  top_posts: Array<{
    platform: string;
    text: string;
    score: number;
    engagement?: number;
    upvotes?: number;
    created_at?: string;
  }>;
  key_themes: string[];
  twitter_score: number;
  reddit_score: number;
  tweet_count: number;
  reddit_post_count: number;
}

export interface AnalysisModule {
  name: string;
  category: "TREND" | "MOMENTUM" | "VOLATILITY" | "VOLUME" | "PATTERN" | "STRUCTURE";
  signal: "BULLISH" | "BEARISH" | "NEUTRAL";
  score_impact: number;
  detail: string;
}

export interface FibonacciLevels {
  swing_high: number;
  swing_low: number;
  level_236: number;
  level_382: number;
  level_500: number;
  level_618: number;
  level_786: number;
  current_zone?: string;
}

export interface TechnicalAnalysis {
  symbol: string;
  analysis_timestamp: string;
  current_price: number;
  rsi_14?: number;
  rsi_signal?: string;
  macd?: number;
  macd_signal?: number;
  macd_histogram?: number;
  macd_crossover?: "BULLISH" | "BEARISH" | "NONE";
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  bb_position?: number;
  bb_squeeze?: boolean;
  ma_20?: number;
  ma_50?: number;
  ma_200?: number;
  ma_trend?: "BULLISH" | "BEARISH";
  golden_cross?: boolean;
  death_cross?: boolean;
  volume_ratio?: number;
  support_levels: number[];
  resistance_levels: number[];
  chart_patterns: string[];
  candlestick_patterns?: string[];
  wyckoff_phase?: string;
  fibonacci_levels?: FibonacciLevels;
  analysis_breakdown?: AnalysisModule[];
  timing_signal: TechnicalSignal;
  entry_price?: number;
  technical_score: number;
  signal_strength: "WEAK" | "MODERATE" | "STRONG";
  signal_reasoning: string;
  data_bars?: number;
  data_source?: "bars" | "info_derived";
  error?: string;
  // info-derived extras
  week52_high?: number;
  week52_low?: number;
  week52_change_pct?: number;
  analyst_consensus_mean?: number;
  short_interest_pct?: number;
  // Charting data (price history + indicator series)
  price_history?: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }>;
  ma20_series?: Array<{ date: string; value: number }>;
  ma50_series?: Array<{ date: string; value: number }>;
  ma200_series?: Array<{ date: string; value: number }>;
  bb_upper_series?: Array<{ date: string; value: number }>;
  bb_lower_series?: Array<{ date: string; value: number }>;
  rsi_series?: Array<{ date: string; value: number }>;
  macd_series?: Array<{ date: string; value: number }>;
  // Elliott Wave
  elliott_wave?: {
    wave_label: string;
    phase: string;
    confidence: "LOW" | "MODERATE" | "HIGH";
    detail: string;
    score_hint?: string;
    pivot_count?: number;
  };
}

export interface Recommendation {
  id: number;
  symbol: string;
  recommendation_type: RecommendationType;
  status: RecommendationStatus;
  confidence_score: number;
  target_price?: number;
  stop_loss?: number;
  current_price_at_recommendation?: number;
  fundamental_analysis?: FundamentalAnalysis;
  fundamental_notes?: string;
  sentiment_data?: SentimentData;
  senior_review_notes?: string;
  senior_notes?: string;
  technical_analysis?: TechnicalAnalysis;
  risk_factors?: string[];
  expected_return_pct?: number;
  trigger_type?: string;
  trigger_details?: string;
  asset_name?: string;
  sector?: string;
  created_at: string;
  approved_at?: string;
  presented_at?: string;
}

export interface UniverseStats {
  universe_total: number;
  seeded_pool: number;
  active_pool: number;
  top_candidates: Array<{ symbol: string; score: number }>;
}

export interface Notification {
  id: number;
  recommendation_id?: number;
  notification_type: NotificationType;
  title?: string;
  external_message: string;
  internal_detail?: {
    recommendation_id?: number;
    symbol?: string;
    recommendation_type?: RecommendationType;
    confidence_score?: number;
    target_price?: number;
    stop_loss?: number;
    fundamental_analysis?: FundamentalAnalysis;
    senior_notes?: string;
    sentiment_summary?: {
      score: number;
      mentions: number;
    };
    [key: string]: any;
  };
  is_read: boolean;
  sent_at: string;
  read_at?: string;
}

export interface WatchlistItem {
  id: number;
  symbol: string;
  asset_id?: number;
  alert_on_technical_signal: boolean;
  last_technical_analysis?: TechnicalAnalysis;
  last_signal_sent_at?: string;
  notes?: string;
  created_at: string;
  asset_name?: string;
  asset_risk_level?: RiskLevel;
  current_price?: number;
  technical_signal?: TechnicalSignal;
  alert_price_above?: number | null;
  alert_price_below?: number | null;
  alert_triggered_at?: string | null;
}

export interface RiskMetrics {
  user_id: number;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  total_value: number;
  total_market_value: number;
  cash_balance: number;
  cash_pct: number;
  total_positions: number;
  herfindahl_index: number;
  diversification_score: number;
  high_risk_exposure_pct: number;
  medium_risk_exposure_pct: number;
  overconcentrated_positions: string[];
  risk_breakdown: Array<{
    symbol: string;
    exposure_pct: number;
    risk_level: string;
    pnl_pct: number;
    current_value: number;
  }>;
  user_risk_profile: RiskProfile;
  user_risk_score: number;
  max_single_asset_pct: number;
  calculated_at: string;
}

export interface RebalancingSuggestion {
  type: "REDUCE_POSITION" | "INCREASE_CASH" | "DIVERSIFY";
  priority: "HIGH" | "MEDIUM" | "LOW";
  symbol?: string;
  current_exposure_pct?: number;
  target_exposure_pct?: number;
  excess_pct?: number;
  current_cash_pct?: number;
  target_cash_pct?: number;
  message: string;
  action: "BUY" | "SELL";
}

export interface ExposureCheck {
  allowed: boolean;
  warning: boolean;
  blocked: boolean;
  current_exposure_pct: number;
  max_allowed_pct: number;
  message: string;
}

// ─── API Pagination ─────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// ─── Onboarding ─────────────────────────────────────────────────────────────

export interface OnboardingData {
  full_name: string;
  email: string;
  password: string;
  phone?: string;
  risk_answers: Record<string, number>;
  risk_profile: RiskProfile;
  risk_score: number;
  initial_deposit: number;
  notification_email: boolean;
  notification_sms: boolean;
  notification_push: boolean;
  preferred_language: "he" | "en";
}

export interface RiskQuestion {
  id: string;
  question_he: string;
  question_en: string;
  options: Array<{
    value: number;
    label_he: string;
    label_en: string;
  }>;
  weight: number;
}

// ─── WebSocket Messages ─────────────────────────────────────────────────────

export type WSMessageType =
  | "connected"
  | "heartbeat"
  | "pong"
  | "new_recommendation"
  | "order_executed"
  | "price_update"
  | "risk_alert";

export interface WSMessage {
  type: WSMessageType;
  timestamp: string;
  data?: any;
}
