import { AI_GOVERNANCE_API_BASE_URL } from "@/lib/api/config";
import { getAuthToken } from "@/auth/token-provider";

type ApiErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
  detail?: unknown | {
    error?: {
      code?: string;
      message?: string;
      details?: unknown;
    };
  };
};

export class AIGovernanceApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor({
    status,
    code,
    message,
    details,
  }: {
    status: number;
    code: string;
    message: string;
    details?: unknown;
  }) {
    super(message);
    this.name = "AIGovernanceApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export type QueryValue = string | number | boolean | null | undefined;

export type QueryParams = Record<string, QueryValue | QueryValue[]>;

function tenantHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const organizationId =
    localStorage.getItem("ai_governance.organization_id") || "org_default";
  const projectId =
    localStorage.getItem("ai_governance.project_id") || "project_default";
  return {
    "X-AI-Governance-Organization-Id": organizationId,
    ...(projectId ? { "X-AI-Governance-Project-Id": projectId } : {}),
  };
}

export async function request(
  path: string,
  init: RequestInit,
  retried = false,
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  const token = await getAuthToken();

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${AI_GOVERNANCE_API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (response.status === 401 && !retried) {
    const refreshedToken = await getAuthToken();

    if (refreshedToken) {
      headers.set("Authorization", `Bearer ${refreshedToken}`);
    }

    return request(
      path,
      {
        ...init,
        headers,
      },
      true,
    );
  }

  return response;
}

export function buildQueryString(params?: QueryParams) {
  if (!params) {
    return "";
  }

  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    const values = Array.isArray(value) ? value : [value];
    values.forEach((item) => {
      if (item !== undefined && item !== null && item !== "") {
        searchParams.append(key, String(item));
      }
    });
  });

  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : "";
}

export async function aiGovernanceRequest<TResponse>(
  path: string,
  params?: QueryParams,
): Promise<TResponse> {
  const response = await request(`${path}${buildQueryString(params)}`, { headers: tenantHeaders(), cache: "no-store" });

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as TResponse;
}

export async function aiGovernanceJsonRequest<TResponse, TBody>(
  path: string,
  {
    method,
    body,
  }: {
    method: "POST" | "PUT" | "PATCH" | "DELETE";
    body?: TBody;
  },
): Promise<TResponse> {
  const response = await request(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...tenantHeaders(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as TResponse;
}

export async function aiGovernanceFormRequest<TResponse>(
  path: string,
  body: FormData,
): Promise<TResponse> {
  const response = await request(path, {
    method: "POST",
    headers: tenantHeaders(),
    body,
    cache: "no-store",
  });

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as TResponse;
}

async function toApiError(response: Response) {
  const fallbackMessage = `AI Governance Control Plane API request failed with status ${response.status}`;
  let payload: ApiErrorEnvelope | null = null;

  try {
    payload = (await response.json()) as ApiErrorEnvelope;
  } catch {
    payload = null;
  }

  const nestedError: ApiErrorEnvelope["error"] | undefined =
    payload?.detail && typeof payload.detail === "object" && "error" in payload.detail
      ? (payload.detail.error as ApiErrorEnvelope["error"])
      : undefined;
  const detailMessage = typeof payload?.detail === "string" ? payload.detail : undefined;

  return new AIGovernanceApiError({
    status: response.status,
    code:
      payload?.error?.code ?? nestedError?.code ??
      (response.status === 404 ? "NOT_FOUND" : "AI_GOVERNANCE_API_ERROR"),
    message: payload?.error?.message ?? nestedError?.message ?? detailMessage ?? fallbackMessage,
    details: payload?.error?.details ?? nestedError?.details ?? payload?.detail,
  });
}
