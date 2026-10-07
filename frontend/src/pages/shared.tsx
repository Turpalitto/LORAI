import React from 'react';
import { onAuthChange, readSession, type Session } from '../lib/auth';

/* Общие помощники страниц: уверенность источника, переход в чат, сессия. */

export function confPill(score: number | undefined): [string, string] {
  if ((score ?? 0) >= 0.5) return ['высокая', 'pill pill-ok'];
  if ((score ?? 0) >= 0.2) return ['средняя', 'pill pill-warn'];
  return ['низкая', 'pill pill-mute'];
}

export function confAnyPill(c: unknown): string {
  if (typeof c === 'number') return confPill(c)[1];
  const s = String(c ?? '').toLowerCase();
  if (s.startsWith('high') || s === 'ok') return 'pill pill-ok';
  if (s.startsWith('med')) return 'pill pill-warn';
  return 'pill pill-mute';
}

export const confLabel = (c: unknown): string =>
  typeof c === 'number' ? c.toFixed(2) : String(c ?? '—');

/** Переход в чат с готовым вопросом (автоотправка — см. Chat). */
export const chatHref = (v: string) => '#/chat?q=' + encodeURIComponent(v);
export const chatHash = (v: string) => { window.location.hash = '#/chat?q=' + encodeURIComponent(v); };

/** Текущая сессия врача с подпиской на вход/выход. */
export function useAuth(): Session | null {
  const [session, setSession] = React.useState<Session | null>(() => readSession());
  React.useEffect(() => onAuthChange(() => setSession(readSession())), []);
  return session;
}

/** Любое брошенное значение приводим к Error — так удобнее в JSX и логах. */
export const toError = (e: unknown): Error => (e instanceof Error ? e : new Error(String(e)));

/** Небольшой загрузчик данных с ручным повтором — без «State update on unmounted». */
export function useAsync<T>(fn: () => Promise<T>, deps: React.DependencyList, enabled = true) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [loading, setLoading] = React.useState(enabled);
  const [nonce, setNonce] = React.useState(0);
  const fnRef = React.useRef(fn);
  fnRef.current = fn;

  React.useEffect(() => {
    if (!enabled) { setLoading(false); setData(null); setError(null); return; }
    let alive = true;
    setLoading(true);
    setError(null);
    fnRef.current()
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(toError(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, nonce]);

  return { data, error, loading, reload: () => setNonce((n) => n + 1) };
}
