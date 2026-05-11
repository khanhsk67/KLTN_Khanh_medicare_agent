// ─── Auth ────────────────────────────────────────────────────────────────────

export interface LoginDto {
  email: string;
  password: string;
}

export interface RegisterDto {
  full_name: string;
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  is_active?: boolean;
  created_at?: string;
}

export type LoginRequest = LoginDto;
export type RegisterRequest = RegisterDto;
export type AuthResponse = TokenResponse;
export type User = UserProfile;


export interface ChatRequest {
  session_id?: string;
  message: string;
  image_base64?: string;
}

export interface SourceChunk {
  content: string;
  source_file?: string;
  relevance_score?: number;
  source?: string;
  score?: number;
}

export interface ChatResponse {
  session_id: string;
  message: string;
  agent_type?: string;
  sources?: SourceChunk[];
}

export interface StreamEvent {
  type: 'start' | 'token' | 'done' | 'error';
  content?: string;
  data?: string;
  session_id?: string;
  urgency_level?: 'normal' | 'warning' | 'emergency';
  sources?: SourceChunk[];
}

export interface MessageItem {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  image_url?: string;
  created_at: string;
  urgency_level?: 'normal' | 'warning' | 'emergency';
  sources?: SourceChunk[];
}

export type ChatMessage = MessageItem;
export type SendMessageRequest = ChatRequest;


export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface SessionWithMessages {
  session: SessionSummary;
  messages: MessageItem[];
}

export interface PaginatedSessions {
  items: SessionSummary[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export type ChatSession = SessionSummary;


export interface AnalysisResponse {
  session_id: string;
  diagnosis: string;
  recommendations: string[];
  confidence: number;
  sources?: SourceChunk[];
}

export interface TimelineEvent {
  date: string;
  event: string;
  severity?: string;
}

export interface HealthTimelineItem {
  id: string;
  date: string;
  main_symptom: string;
  specialty?: string;
  severity: 'severe' | 'moderate' | 'mild';
  session_id: string;
}

export interface HealthDashboard {
  period_days: number;
  total_sessions: number;
  total_messages: number;
  avg_messages_per_session: number;
  top_symptoms: Array<{ name: string; count: number }>;
  severity_distribution: { severe: number; moderate: number; mild: number };
  consultation_frequency: Array<{ date: string; count: number }>;
  ai_insight?: string;
}

export interface DetailedStats {
  total_sessions: number;
  total_messages: number;
  avg_messages_per_session: number;
  most_common_topics?: string[];
}

export type AnalysisResult = AnalysisResponse;


export interface HealthRiskResponse {
  city: string;
  temperature: number;
  humidity: number;
  condition: string;
  risk_level: string;
  risk_diseases: string[];
  advice: string;
  cached?: boolean;
}
