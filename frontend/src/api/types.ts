/**
 * Response contracts, mirrored from the live OpenAPI document
 * (http://localhost:5000/openapi.json) so nothing here is guesswork.
 */

export type AnalysisStatus = 'success' | 'no_data' | 'failed';
export type QueryStatus = 'success' | 'failed';

export interface QueryData {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  total_rows: number;
  truncated: boolean;
}

export interface SQLExecutionResult {
  tool_call_id: string;
  requested_sql: string;
  executed_sql: string | null;
  status: QueryStatus;
  data: QueryData | null;
  error: string | null;
}

export interface DescribeTableData {
  table_name: string;
  schema: string | null;
  columns: Array<{ name: string; type: string; nullable: boolean }>;
  primary_key: string[];
  foreign_keys: Array<{
    columns: string[];
    referred_schema: string | null;
    referred_table: string;
    referred_columns: string[];
  }>;
}

export type SchemaToolData = string[] | DescribeTableData;

export interface SchemaToolResult {
  tool_call_id: string;
  tool_name: 'list_tables' | 'describe_table';
  status: QueryStatus;
  data: SchemaToolData | null;
  error: string | null;
}

export interface AnalysisMetadata {
  dialect: string;
  tools_used: string[];
}

export interface AnalysisResponse {
  status: AnalysisStatus;
  answer: string | null;
  queries: SQLExecutionResult[];
  metadata: AnalysisMetadata;
  schema_results: SchemaToolResult[];
  error: string | null;
  conversation_id: string | null;
}

export interface ConnectionResponse {
  status: 'connected' | 'disconnected';
  dialect: string | null;
  connection_id: string | null;
}

export interface ConversationSummary {
  id: string;
  connection_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface MessageRecord {
  id: string;
  conversation_id: string;
  role: string;
  content: string | null;
  status: string | null;
  queries: SQLExecutionResult[] | null;
  schema_results: SchemaToolResult[] | null;
  metadata: AnalysisMetadata | null;
  error: string | null;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: MessageRecord[];
}
