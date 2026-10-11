export const API = import.meta.env.VITE_API || "http://localhost:8000";
export const TOKEN_KEY = "campus_gate_guard_token";
export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const setToken = (token) => token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY);
export const todayIST = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
export const cleanPlate = (s) => (s || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
export const PLATE_RE = /^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$/;

export function errorText(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1) || "field"}: ${(d.msg || "Invalid value").replace("Value error, ", "")}`).join(" · ");
  return "Something went wrong";
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const r = await fetch(API + path, { ...options, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401 && token) {
      setToken(null);
      if (location.hash.startsWith("#/guard/")) location.hash = "#/guard/login";
    }
    throw new Error(errorText(data.detail) || `${path} failed (${r.status})`);
  }
  return data;
}
export const getJSON = (path) => request(path);
export const register = (body) => request("/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const login = (username, password) => request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
export const logout = () => request("/auth/logout", { method: "POST" });
export async function scan(blob) {
  const fd = new FormData(); fd.append("file", blob, blob.name || "frame.jpg");
  return request("/scan", { method: "POST", body: fd });
}

export const saveManualDecision = (body) => request("/manual-decision", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const addFleetVehicle = (body) => request("/fleet/vehicles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const deleteFleetVehicle = (id) => request(`/fleet/vehicles/${id}`, { method: "DELETE" });
