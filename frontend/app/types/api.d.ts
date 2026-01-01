interface User {
  id: string;
  email: string;
  name: string;
  avatar_url: string;
  is_active?: boolean;
  is_superuser?: boolean;
  is_verified?: boolean;
  created_at: string;
}

interface Message {
  id: string;
  content: string;
  message_type: "USER" | "ASSISTANT";
  created_at: string;
  user_message_id?: string;
  status?: "STREAMING" | "FINAL";
  extra_data?: Record<string, any>;
}

interface ChatSession {
  id: string;
  assistant_id: string;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

interface ChatResponse {
  message: string;
  conversation_updated: boolean;
  conversation_id: string;
}

interface ChatRequest {
  assistant_id: string;
  content: string;
  conversation_id?: string;
  stream?: boolean;
}

interface SendMessageRequest {
  content: string;
  assistant_id: string;
}

interface Conversation {
  id: string;
  title: string;
  assistant_id: string;
  user_id: string;
  status: string;
  last_message_at: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
  assistant_name?: string;
}

interface ConversationShareResponse {
  id: string;
  conversation_id: string;
  scope: "CONVERSATION" | "MESSAGE";
  status: "ACTIVE" | "REVOKED";
  start_message_id?: string | null;
  end_message_id?: string | null;
  created_at: string;
  updated_at: string;
}

interface ConversationSharePublicResponse {
  id: string;
  conversation_id: string;
  scope: "CONVERSATION" | "MESSAGE";
  assistant_id?: string | null;
  assistant_name: string;
  assistant_description?: string | null;
  assistant?: SharedAssistant | null;
  conversation_title: string;
  messages: Message[];
  created_at: string;
}

interface SharedAssistant {
  id: string;
  name: string;
  description?: string | null;
  avatar_file_path?: string | null;
  avatar_url?: string | null;
  translations?: Record<string, Record<string, string>>;
}

interface GenerateTitleResponse {
  conversation_id: string;
  title: string;
}

interface PaginatedResponse<T> {
  total: number;
  page: number;
  size: number;
  pages: number;
  items: T[];
}

type ConversationsResponse = PaginatedResponse<Conversation>;

export interface PublicConfig {
  registration_enabled: boolean;
  allow_user_create_assistants?: boolean;
  ui_show_share_button?: boolean;
  ui_show_message_share_button?: boolean;
  ui_show_message_feedback_buttons?: boolean;
  ui_show_message_stats?: boolean;
  ui_show_pin_button?: boolean;
  ui_show_create_button?: boolean;
  ui_show_assistant_dropdown?: boolean;
  ui_show_agent_thinking?: boolean;
  ui_show_chat_suggestions?: boolean;
  ui_generate_followup_questions?: boolean;
  ui_followup_question_count?: number;
  ui_show_signup_terms?: boolean;
}

export interface ConfigResponse {
  configs: PublicConfig;
}

export interface SystemConfigItem {
  id: string;
  key: string;
  value: any;
  description?: string | null;
  is_public: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemConfigListResponse {
  configs: SystemConfigItem[];
  total: number;
}

export interface AnalyticsStatsResponse {
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_execution_time_ms: number;
  avg_execution_time_ms: number;
  daily_tokens: Array<{ date: string; [key: string]: number | string }>;
  daily_requests: ChartDataPoint[];
  daily_latency: ChartDataPoint[];
}

// ModelView related types
export interface ModelViewApiResponse<T = any> {
  success: boolean;
  data?: T;
  message?: string;
  errors?: Record<string, string[]>;
}

export interface ModelViewQueryParams {
  page?: number;
  size?: number;
  search?: string;
  sort_by?: string;
  sort_desc?: boolean;
  [key: string]: any;
}

export interface ModelViewBulkOperation {
  action: string;
  ids: (string | number)[];
  data?: any;
}

interface Provider {
  id: string;
  template_id?: string;
  name: string;
  display_name: string;
  description: string;
  website: string;
  api_base_url: string;
  api_key?: string;
  interface_type: string;
  litellm_provider?: string;
  status: "ACTIVE" | "INACTIVE" | "MAINTENANCE";
  created_at: string;
}

interface Model {
  id: string;
  template_id?: string;
  name: string;
  display_name: string;
  description: string;
  status: "ACTIVE" | "INACTIVE" | "UNAVAILABLE" | "DEPRECATED";
  provider_id: string;
  max_context_tokens: number;
  max_output_tokens: number;
  capabilities?: string[];
  generation_config?: Record<string, any>;
  created_at: string;
  provider?: Provider;
}

interface RagConfig {
  retrieval_count: number;
  fetch_k?: number;
  similarity_threshold?: number;
  search_type?: string;
  mmr_lambda?: number;
  context_max_tokens?: number;
  skip_smalltalk?: boolean;
  skip_patterns?: string[];
  multi_query?: boolean;
  multi_query_count?: number;
  rerank_top_k?: number;
  rerank_model_id?: string;
  hybrid_enabled?: boolean;
  hybrid_corpus_limit?: number;
}

interface Assistant {
  id: string;
  name: string;
  description: string;
  avatar_url?: string;
  avatar_file_path?: string;
  model_id: string;
  owner_id: string;
  owner_name?: string;
  system_prompt: string;
  mode?: "GENERAL" | "RAG";
  use_global_generation_defaults?: boolean;
  use_global_rag_defaults?: boolean;
  config?: Record<string, any>;
  followup_questions_enabled?: boolean;
  followup_questions_count?: number | null;
  temperature: number;
  max_tokens: number;
  max_history_messages?: number;
  status: "ACTIVE" | "INACTIVE" | "DRAFT";
  is_public: boolean;
  created_at: string;
  updated_at: string;
  model?: Model;
  // Knowledge base related fields
  knowledge_base_ids?: string[];
  rag_config?: RagConfig;
  is_pinned?: boolean;
  translations?: Record<string, Record<string, string>>;
}

interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_model_id?: string;
  embedding_model_name?: string;
  chunk_size?: number;
  chunk_overlap?: number;
  reindex_required?: boolean;
  status?: string;
  created_at: string;
  updated_at: string;
}

interface Document {
  id: string;
  title: string;
  content?: string;
  file_path?: string;
  file_name?: string;
  file_size?: number;
  file_type: string;
  knowledge_base_id: string;
  status: "INDEXING" | "ACTIVE" | "FAILED";
  created_at: string;
  updated_at: string;
}

interface FileUploadResponse {
  file_path: string;
  file_name: string;
  file_size: number;
  mime_type: string;
}

// OAuth provider interface definition
interface OAuthProvider {
  id?: string;
  name: string;
  display_name: string;
  description?: string;
  client_id: string;
  client_secret: string;
  auth_url: string;
  token_url: string;
  user_info_url: string;
  scopes: string[];
  user_mapping: Record<string, string>;
  icon_url?: string;
  sort_order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

// Agent tool interface definition
interface LocalTool {
  name: string;
  description: string;
}

interface MCPServer {
  id: string;
  name: string;
  description: string;
}

interface AvailableAgentTools {
  local_tools: LocalTool[];
  mcp_servers: MCPServer[];
}
