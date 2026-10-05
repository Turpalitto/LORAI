export const API = (import.meta as any).env.VITE_API_URL || 'http://localhost:8000';
export const DISC = 'Инструмент носит вспомогательный справочный характер. Решение принимает врач. Не вводите персональные данные пациента.';
export async function api(path: string, opts: any = {}) {
  const t = localStorage.getItem('token');
  const r = await fetch(API + path, { ...opts, headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: 'Bearer ' + t } : {}), ...(opts.headers || {}) } });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
export const login = (email: string, password: string) => api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
