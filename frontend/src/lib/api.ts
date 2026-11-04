import type {
  AnalyzeResponse,
  BusinessProfile,
  ContactRequest,
  CreativeResponse,
  DataQuality,
  ErrorResponse,
  ProfileResponse,
  ReportListResponse,
  StatusResponse,
} from "../types/api";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

export class AnalyzeError extends Error {
  code: string;
  retryable: boolean;
  status: number;
  retryAfter?: number;

  constructor(
    message: string,
    code: string,
    retryable: boolean,
    status: number,
    retryAfter?: number,
  ) {
    super(message);
    this.name = "AnalyzeError";
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.code === "string" &&
    typeof record.message === "string" &&
    typeof record.retryable === "boolean"
  );
}

function isAnalyzeResponse(value: unknown): value is AnalyzeResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const quality: unknown = record.data_quality;
  const qualities: DataQuality[] = ["full", "partial", "og_only"];
  return (
    typeof record.request_id === "string" &&
    typeof record.summary === "string" &&
    Array.isArray(record.issues) &&
    Array.isArray(record.rewrites) &&
    Array.isArray(record.limitations) &&
    qualities.some((entry) => entry === quality)
  );
}

function networkError(host = "server"): AnalyzeError {
  return new AnalyzeError(
    `Could not reach the ${host}. Check your connection and try again.`,
    "NETWORK_ERROR",
    true,
    0,
  );
}

function errorFromPayload(response: Response, payload: unknown): AnalyzeError {
  if (isErrorResponse(payload)) {
    const header = response.headers.get("Retry-After");
    const parsed = header === null ? NaN : Number.parseInt(header, 10);
    const retryAfter = Number.isNaN(parsed) ? undefined : parsed;
    return new AnalyzeError(
      payload.message,
      payload.code,
      payload.retryable,
      response.status,
      retryAfter,
    );
  }
  return new AnalyzeError(
    `The server returned status ${response.status}. Try again in a minute.`,
    "SERVER_ERROR",
    response.status >= 500,
    response.status,
  );
}

function badResponse(status: number): AnalyzeError {
  return new AnalyzeError(
    "The server returned an unexpected response. Try again in a minute.",
    "BAD_RESPONSE",
    true,
    status,
  );
}

export async function analyzeUrl(
  url: string,
  brandVoice: string,
  signal: AbortSignal,
  idToken?: string,
): Promise<AnalyzeResponse> {
  const params = new URLSearchParams();
  const voice = brandVoice.trim();
  if (voice !== "") params.set("brand_voice", voice.slice(0, 2000));
  const query = params.size > 0 ? `?${params.toString()}` : "";
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (idToken) headers["Authorization"] = `Bearer ${idToken}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/analyze${query}`, {
      method: "POST",
      headers,
      body: JSON.stringify({ url }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw networkError("analysis server");
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw errorFromPayload(response, payload);
  if (!isAnalyzeResponse(payload)) throw badResponse(response.status);
  return payload;
}

interface ApiOptions {
  method: "GET" | "POST" | "PUT" | "DELETE";
  token?: string;
  body?: unknown;
  signal?: AbortSignal;
}

async function requestJson<T>(
  path: string,
  options: ApiOptions,
  isExpected: (value: unknown) => value is T,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw networkError();
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw errorFromPayload(response, payload);
  if (!isExpected(payload)) throw badResponse(response.status);
  return payload;
}

function isStatusResponse(value: unknown): value is StatusResponse {
  if (typeof value !== "object" || value === null) return false;
  return typeof (value as Record<string, unknown>).status === "string";
}

function isReportListResponse(value: unknown): value is ReportListResponse {
  if (typeof value !== "object" || value === null) return false;
  const reports = (value as Record<string, unknown>).reports;
  if (!Array.isArray(reports)) return false;
  return reports.every(
    (entry) =>
      typeof entry === "object" &&
      entry !== null &&
      typeof (entry as Record<string, unknown>).id === "string" &&
      typeof (entry as Record<string, unknown>).url === "string" &&
      typeof (entry as Record<string, unknown>).summary === "string",
  );
}

export async function sendContactMessage(input: ContactRequest): Promise<StatusResponse> {
  return requestJson("/api/contact", { method: "POST", body: input }, isStatusResponse);
}

export async function fetchReports(token: string): Promise<ReportListResponse> {
  return requestJson("/api/reports", { method: "GET", token }, isReportListResponse);
}

export async function deleteReport(token: string, id: string): Promise<StatusResponse> {
  return requestJson(
    `/api/reports/${encodeURIComponent(id)}`,
    { method: "DELETE", token },
    isStatusResponse,
  );
}

export async function deleteAccount(token: string): Promise<StatusResponse> {
  return requestJson("/api/account", { method: "DELETE", token }, isStatusResponse);
}

function isProfileResponse(value: unknown): value is ProfileResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  if (typeof record.profile_complete !== "boolean") return false;
  if (record.profile === null) return true;
  if (typeof record.profile !== "object" || record.profile === null) return false;
  const profile = record.profile as Record<string, unknown>;
  return (
    typeof profile.business_name === "string" &&
    typeof profile.website === "string" &&
    typeof profile.industry === "string" &&
    typeof profile.city === "string" &&
    typeof profile.country === "string" &&
    typeof profile.size === "string" &&
    typeof profile.role === "string"
  );
}

export async function fetchProfile(token: string): Promise<ProfileResponse> {
  return requestJson("/api/profile", { method: "GET", token }, isProfileResponse);
}

export async function saveProfile(
  token: string,
  profile: BusinessProfile,
): Promise<ProfileResponse> {
  return requestJson("/api/profile", { method: "PUT", token, body: profile }, isProfileResponse);
}

function isCreativeResponse(value: unknown): value is CreativeResponse {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  const quality: unknown = record.data_quality;
  const qualities: DataQuality[] = ["full", "partial", "og_only"];
  return (
    typeof record.request_id === "string" &&
    (record.source === "image" || record.source === "youtube") &&
    typeof record.platform === "string" &&
    typeof record.summary === "string" &&
    Array.isArray(record.issues) &&
    Array.isArray(record.limitations) &&
    qualities.some((entry) => entry === quality)
  );
}

async function requestForm<T>(
  path: string,
  token: string,
  form: FormData,
  signal: AbortSignal,
  isExpected: (value: unknown) => value is T,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw networkError();
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw errorFromPayload(response, payload);
  if (!isExpected(payload)) throw badResponse(response.status);
  return payload;
}

export async function analyzeCreative(
  token: string,
  input: {
    platform: string;
    goal: string;
    youtubeUrl: string;
    image: File | null;
  },
  signal: AbortSignal,
): Promise<CreativeResponse> {
  const form = new FormData();
  form.set("platform", input.platform);
  form.set("goal", input.goal);
  form.set("youtube_url", input.youtubeUrl);
  if (input.image !== null) form.set("image", input.image);
  return requestForm("/api/creative/analyze", token, form, signal, isCreativeResponse);
}

export async function improveCreative(
  token: string,
  input: { image: File; headline: string; subtext: string; cta: string },
  signal: AbortSignal,
): Promise<Blob> {
  const form = new FormData();
  form.set("image", input.image);
  form.set("headline", input.headline);
  form.set("subtext", input.subtext);
  form.set("cta", input.cta);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/creative/improve`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw networkError();
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw errorFromPayload(response, payload);
  }
  return response.blob();
}
