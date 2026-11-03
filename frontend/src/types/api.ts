// Fix It Proper API contract, mirrors backend/app/schemas.py field for field.
// Backend validates http/https for AnalyzeRequest.url; frontend sends a string.
// Backend fetched_at is datetime; frontend uses ISO 8601 string.

export type DataQuality = "full" | "partial" | "og_only";

export type IssueCategory =
  | "seo"
  | "content"
  | "technical"
  | "performance"
  | "accessibility";

export type Severity = "high" | "medium" | "low";

export type EvidenceType = "text" | "selector" | "metric";

export type RewriteTarget = "title" | "meta_description" | "h1" | "cta";

export type RewriteLabel = "AI generated, test before using";

export interface AnalyzeRequest {
  url: string;
}

export interface Evidence {
  type: EvidenceType;
  value: string;
}

export interface Issue {
  id: string;
  category: IssueCategory;
  title: string;
  severity: Severity;
  confidence: number;
  evidence: Evidence;
  source: string;
  why_it_matters: string;
  suggested_fix: string;
  impact_rank: number;
}

export interface Rewrite {
  target: RewriteTarget;
  original: string;
  variants: string[];
  label: RewriteLabel;
}

export interface ScoreComponent {
  name: string;
  value: number;
  weight: number;
}

export interface Score {
  value: number;
  formula_version: string;
  components: ScoreComponent[];
}

export interface AnalyzeResponse {
  request_id: string;
  url: string;
  fetched_at: string;
  data_quality: DataQuality;
  summary: string;
  issues: Issue[];
  rewrites: Rewrite[];
  limitations: string[];
  score?: Score | null;
}

export interface ErrorResponse {
  code: string;
  message: string;
  retryable: boolean;
}

export interface ContactRequest {
  name: string;
  email: string;
  message: string;
  company?: string;
}

export interface StatusResponse {
  status: string;
}

export interface ReportSummary {
  id: string;
  url: string;
  data_quality: DataQuality;
  summary: string;
  issue_count: number;
  score_value: number | null;
  created_at: string;
}

export interface ReportListResponse {
  reports: ReportSummary[];
}
