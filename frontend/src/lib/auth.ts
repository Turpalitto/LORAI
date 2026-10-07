/* Сессия врача: токен, роль, срок действия — в одном месте.
   Раньше про токен знал только раздел «Админ»: история и избранное молча
   отвечали 401, а в шапке не было видно, вошёл ли пользователь. */
import { store } from './storage';

export type Role = 'admin' | 'doctor' | 'guest';
export interface Session {
  token: string;
  email: string;
  role: Role;
  /** Unix-время истечения (сек) или null, если в токене нет exp. */
  exp: number | null;
}

const TOKEN_KEY = 'token';
export const AUTH_EVENT = 'lorai-auth';

function b64urlDecode(part: string): string {
  const pad = part.length % 4 === 0 ? '' : '='.repeat(4 - (part.length % 4));
  const b64 = part.replace(/-/g, '+').replace(/_/g, '/') + pad;
  // atob есть и в браузере, и в Node 18+ (нужен для vitest).
  return typeof atob === 'function' ? atob(b64) : Buffer.from(b64, 'base64').toString('binary');
}

/** Разбор payload JWT без проверки подписи (подпись проверяет сервер). */
export function decodeJwt(token: string): Record<string, any> | null {
  const parts = (token || '').split('.');
  if (parts.length !== 3) return null;
  try {
    const json = decodeURIComponent(
      b64urlDecode(parts[1])
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    );
    const payload = JSON.parse(json);
    return payload && typeof payload === 'object' ? payload : null;
  } catch {
    return null;
  }
}

/** Текущая сессия или null. Просроченный токен удаляется сразу. */
export function readSession(now = Date.now() / 1000): Session | null {
  const token = store.get(TOKEN_KEY);
  if (!token) return null;
  const p = decodeJwt(token);
  if (!p) { store.remove(TOKEN_KEY); return null; }
  const exp = typeof p.exp === 'number' ? p.exp : null;
  if (exp !== null && exp <= now) { store.remove(TOKEN_KEY); return null; }
  const role = (p.role === 'admin' || p.role === 'doctor' ? p.role : 'doctor') as Role;
  return { token, email: String(p.sub || ''), role, exp };
}

export function saveToken(token: string): Session | null {
  store.set(TOKEN_KEY, token);
  const s = readSession();
  window.dispatchEvent(new Event(AUTH_EVENT));
  return s;
}

export function clearSession(): void {
  store.remove(TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

/** Подписка на вход/выход; возвращает функцию отписки. */
export function onAuthChange(cb: () => void): () => void {
  window.addEventListener(AUTH_EVENT, cb);
  window.addEventListener('storage', cb);
  return () => {
    window.removeEventListener(AUTH_EVENT, cb);
    window.removeEventListener('storage', cb);
  };
}

export const roleLabel = (r: Role): string =>
  r === 'admin' ? 'администратор' : r === 'doctor' ? 'врач' : 'гость';

/** Сколько осталось до конца сессии — для ненавязчивой подсказки в шапке. */
export function expiresInText(exp: number | null, now = Date.now() / 1000): string {
  if (!exp) return '';
  const left = Math.max(0, Math.round(exp - now));
  if (left === 0) return 'сессия истекла';
  if (left < 3600) return `сессия ещё ${Math.max(1, Math.round(left / 60))} мин`;
  if (left < 86400) return `сессия ещё ${Math.round(left / 3600)} ч`;
  return `сессия ещё ${Math.round(left / 86400)} дн`;
}
