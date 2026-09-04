/**
 * Centralized API client wrapper with standardized error and JSON handling.
 */

export const API_BASE = 'http://localhost:8000/api';

export class ApiClientError extends Error {
  status: number;
  statusText: string;
  detail: any;

  constructor(status: number, statusText: string, detail: any) {
    let message = `API Error ${status} (${statusText})`;
    if (typeof detail === 'string') {
      message = detail;
    } else if (detail && typeof detail === 'object') {
      if (typeof detail.detail === 'string') {
        message = detail.detail;
      } else if (typeof detail.message === 'string') {
        message = detail.message;
      } else {
        message = JSON.stringify(detail);
      }
    }
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.statusText = statusText;
    this.detail = detail;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail: any;
    try {
      errorDetail = await res.json();
    } catch {
      errorDetail = await res.text();
    }
    throw new ApiClientError(res.status, res.statusText, errorDetail);
  }

  // Handle empty bodies (e.g. 204 No Content)
  const contentType = res.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return (await res.json()) as T;
  }

  const text = await res.text();
  return (text ? JSON.parse(text) : ({} as T)) as T;
}

function buildUrl(path: string, params?: Record<string, string | number | boolean | undefined | null>): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${API_BASE}${cleanPath}`);

  if (params) {
    Object.entries(params).forEach(([key, val]) => {
      if (val !== undefined && val !== null) {
        url.searchParams.append(key, String(val));
      }
    });
  }

  return url.toString();
}

export const apiClient = {
  async get<T>(path: string, params?: Record<string, string | number | boolean | undefined | null>): Promise<T> {
    const res = await fetch(buildUrl(path, params), {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });
    return handleResponse<T>(res);
  },

  async post<T>(path: string, body?: unknown, params?: Record<string, string | number | boolean | undefined | null>): Promise<T> {
    const res = await fetch(buildUrl(path, params), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(res);
  },

  async put<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(buildUrl(path), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(res);
  },

  async patch<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(buildUrl(path), {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    return handleResponse<T>(res);
  },

  async delete<T>(path: string): Promise<T> {
    const res = await fetch(buildUrl(path), {
      method: 'DELETE',
      headers: {
        'Accept': 'application/json',
      },
    });
    return handleResponse<T>(res);
  },
};
