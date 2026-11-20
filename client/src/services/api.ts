import type {
  StudentSummary,
  StudentResponse,
  ClassResponse,
  ManualPredictionRequest,
  ManualPredictionResponse,
} from "../types";

const configuredApiUrl = import.meta.env.VITE_API_BASE_URL;
// Render's service-host value has no protocol; localhost remains the development default.
const API_BASE_URL = configuredApiUrl
  ? (/^https?:\/\//.test(configuredApiUrl) ? configuredApiUrl : `https://${configuredApiUrl}`)
  : "http://127.0.0.1:8000";

export interface AuthUser { id: number; username: string; role: "admin" | "faculty"; full_name: string; }
const token = () => localStorage.getItem("spi_token");
const authHeaders = (): Record<string, string> => {
  const value = token();
  return value ? { Authorization: `Bearer ${value}` } : {};
};
const apiError = async (res: Response) => {
  const data = await res.json().catch(() => ({}));
  throw new Error(data.detail || `Request failed (${res.status})`);
};

export const login = async (username: string, password: string) => {
  const res = await fetch(`${API_BASE_URL}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
  if (!res.ok) await apiError(res);
  return await res.json() as { access_token: string; user: AuthUser };
};
export const getCurrentUser = async (): Promise<AuthUser> => {
  const res = await fetch(`${API_BASE_URL}/auth/me`, { headers: authHeaders() });
  if (!res.ok) await apiError(res);
  return await res.json();
};
export const logout = () => localStorage.removeItem("spi_token");

export const checkBackendHealth = async (): Promise<boolean> => {
  try {
    const res = await fetch(`${API_BASE_URL}/`, { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
};

export const fetchStudentsList = async (): Promise<StudentSummary[]> => {
  try {
    const res = await fetch(`${API_BASE_URL}/students`, { headers: authHeaders() });
    if (!res.ok) throw new Error("Failed to fetch students");
    const data = await res.json();
    return data.students || [];
  } catch {
    return [];
  }
};

export const fetchClassesList = async (): Promise<string[]> => {
  try {
    const res = await fetch(`${API_BASE_URL}/classes`, { headers: authHeaders() });
    if (!res.ok) throw new Error("Failed to fetch classes");
    const data = await res.json();
    return data.classes || ["10A", "10B", "10C"];
  } catch {
    return [];
  }
};

export const getStudentData = async (studentId: string): Promise<StudentResponse> => {
  const res = await fetch(`${API_BASE_URL}/student/${encodeURIComponent(studentId)}`, { headers: authHeaders() });
  if (res.status === 404) {
    throw new Error(`Student '${studentId}' not found.`);
  }
  if (!res.ok) {
    await apiError(res);
  }
  return await res.json();
};

export const getClassData = async (classId: string): Promise<ClassResponse> => {
  const res = await fetch(`${API_BASE_URL}/class/${encodeURIComponent(classId)}`, { headers: authHeaders() });
  if (res.status === 404) {
    throw new Error(`Class '${classId}' not found.`);
  }
  if (!res.ok) {
    throw new Error(`API Error: ${res.status} ${res.statusText}`);
  }
  return await res.json();
};

export const generateManualPrediction = async (
  payload: ManualPredictionRequest
): Promise<ManualPredictionResponse> => {
  const res = await fetch(`${API_BASE_URL}/manual-prediction`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Prediction failed: ${errText}`);
  }

  return await res.json();
};

export const saveMarks = async (payload: Record<string, unknown>) => {
  const res = await fetch(`${API_BASE_URL}/marks`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify(payload) });
  if (!res.ok) await apiError(res);
  return res.json();
};

export const getFacultyDashboard = async () => {
  const res = await fetch(`${API_BASE_URL}/faculty/dashboard`, { headers: authHeaders() });
  if (!res.ok) await apiError(res);
  return res.json();
};

export const adminRequest = async (path: string, method = "GET", body?: unknown) => {
  const res = await fetch(`${API_BASE_URL}${path}`, { method, headers: { ...authHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) }, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) await apiError(res);
  return res.status === 204 ? undefined : res.json();
};
