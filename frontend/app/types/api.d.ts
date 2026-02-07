interface User {
  id: string;
  email: string;
  name: string;
  avatar_url: string;
  is_active?: boolean;
  is_superuser?: boolean;
  is_verified?: boolean;
  role?: "admin" | "editor" | "viewer" | null;
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
  // Message editing fields
  edited_at?: string | null;
  original_content?: string | null;
  is_regenerated?: boolean;
  parent_message_id?: string | null;
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
  ai_registry_allow_external?: boolean;
  ui_show_model_selector?: boolean;
  ui_show_web_search_toggle?: boolean;
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
  category: "OPENAI_COMPATIBLE" | "PROVIDER_SPECIFIC" | "CUSTOM" | "LOCAL";
  is_openai_compatible: boolean;
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
  // Agent related fields
  enable_agent?: boolean;
  agent_max_iterations?: number;
  agent_enabled_tools?: string[];
  agent_tool_config?: Record<string, any>;
  mcp_server_ids?: string[];
  // Agent budget controls
  agent_token_budget?: number;
  agent_max_tool_calls?: number;
  agent_cost_limit_usd?: number;
  agent_max_parallel_tools?: number;
  // Agent behavior settings
  agent_enable_planning?: boolean;
  agent_enable_reflection?: boolean;
  agent_reflection_threshold?: number;
  // Memory settings
  enable_memory?: boolean;
  // Multi-agent settings
  specialist_type?: "RESEARCH" | "CODE" | "DATA" | "GENERAL" | null;
  can_collaborate?: boolean;
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
  description: string | null;
  server_type: "STDIO" | "SSE" | "HTTP";
  connection_config: Record<string, any>;
  is_active: boolean;
  extra_data: Record<string, any>;
  created_at: string;
  updated_at: string;
}

interface MCPServerEnvVar {
  name: string;
  description: string | null;
  docs_url: string | null;
  is_set: boolean;
  value_preview: string | null;
}

interface MCPServerEnvCheckResponse {
  server_name: string;
  all_vars_set: boolean;
  env_vars: MCPServerEnvVar[];
  setup_instructions: string | null;
}

interface MCPServerHealthResponse {
  server_id: string;
  server_name: string;
  is_active: boolean;
  is_healthy: boolean;
  status: "healthy" | "unhealthy" | "unconfigured" | "inactive" | "error";
  message: string;
  last_check_ms: number | null;
  tools_count: number | null;
}

interface MCPServerTestResponse {
  success: boolean;
  message: string;
  tools_count: number | null;
  latency_ms: number | null;
}

interface AvailableAgentTools {
  local_tools: LocalTool[];
  mcp_servers: MCPServer[];
}

// Document Preprocessing Types (Smart Document Preprocessing)
interface DocumentPreprocessingConfig {
  // PDF options
  pdf_max_pages?: number;
  pdf_page_range?: string;
  pdf_enable_ocr?: boolean;
  // Excel/CSV options
  sheet_names?: string[];
  header_row?: number;
  skip_rows?: number;
  // Chunking options
  chunking_strategy?: "auto" | "semantic" | "hierarchical" | "sentence";
  chunk_size_override?: number;
  chunk_overlap_override?: number;
  // General options
  extract_tables_as_markdown?: boolean;
  clean_data?: boolean;
}

interface PdfInfoResponse {
  page_count: number;
  file_size_bytes: number;
  has_text: boolean;
  title?: string;
  author?: string;
  is_encrypted: boolean;
}

interface ExcelSheetInfo {
  name: string;
  row_count: number;
  column_count: number;
  columns: string[];
}

interface ExcelSheetsResponse {
  sheets: ExcelSheetInfo[];
  file_name?: string;
}

interface PreviewRowsResponse {
  sheet_name?: string;
  rows: Record<string, any>[];
  columns: string[];
  total_rows: number;
}
