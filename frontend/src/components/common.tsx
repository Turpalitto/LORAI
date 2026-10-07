import React from 'react';
import { DISC, humanError } from '../api/client';

/* ---------- Баннер ПДн ---------- */
export function Banner() {
  return (
    <div className="banner" role="note" aria-label="Предупреждение о персональных данных">
      <span aria-hidden="true">⚠️</span>
      <span>{DISC}</span>
    </div>
  );
}

/* ---------- Кнопки и контейнеры ---------- */
export function Button({
  children, loading, variant, ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; variant?: 'secondary' | 'ghost' | 'danger' }) {
  const cls = 'btn' + (variant === 'secondary' ? ' btn-secondary' : variant === 'ghost' ? ' btn-ghost' : variant === 'danger' ? ' btn-danger' : '');
  return (
    <button className={cls} disabled={loading || rest.disabled} aria-busy={!!loading} {...rest}>
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}

export function Card({ children, labelledBy, className }: { children: React.ReactNode; labelledBy?: string; className?: string }) {
  return (
    <section className={'card' + (className ? ' ' + className : '')} aria-labelledby={labelledBy}>
      {children}
    </section>
  );
}

export function PageHeader({ title, sub, id }: { title: string; sub?: string; id: string }) {
  return (
    <div className="page-head">
      <h2 id={id}>{title}</h2>
      {sub && <p className="muted">{sub}</p>}
    </div>
  );
}

/* ---------- Состояния: загрузка / пусто / ошибка ---------- */
export function Skeleton({ lines = 3, label = 'Загрузка данных' }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="skeleton-box">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 22 : 16, opacity: 1 - i * 0.12 }} />
      ))}
      <span className="caption">{label}…</span>
    </div>
  );
}

export function Empty({ title, hint, action }: { title?: string; hint: string; action?: React.ReactNode }) {
  return (
    <div className="empty" role="status">
      <div>
        {title && <b>{title}</b>}
        <div style={{ fontSize: 14 }}>{hint}</div>
        {action && <div className="row" style={{ marginTop: 12 }}>{action}</div>}
      </div>
    </div>
  );
}

export function ErrorBox({ error, onRetry, hint }: { error: unknown; onRetry?: () => void; hint?: React.ReactNode }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert">
      <b>Не получилось.</b> {humanError(error)}
      {hint && <div className="caption" style={{ marginTop: 6 }}>{hint}</div>}
      {onRetry && (
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="secondary" onClick={onRetry}>Повторить</Button>
        </div>
      )}
    </div>
  );
}

/* ---------- Требуется вход ---------- */
export function LoginRequired({ what = 'этот раздел' }: { what?: string }) {
  return (
    <div className="panel panel-info login-required" role="status">
      <div>
        <b>Нужен вход в систему.</b>{' '}
        <span className="muted">История запросов, избранное и отчёты хранятся на сервере и доступны только врачу с сессией.</span>
      </div>
      <a className="btn btn-sm" href="#/login">Войти</a>
    </div>
  );
}

/* ---------- Полоса прогресса ---------- */
export function Progress({ value, max, label }: { value: number; max: number; label?: string }) {
  const pct = max > 0 ? Math.round((Math.min(value, max) / max) * 100) : 0;
  return (
    <div className="progress-wrap">
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={max} aria-valuenow={value}
        aria-label={label || 'Прогресс'}>
        <i style={{ width: pct + '%' }} />
      </div>
      {label && <span className="caption num">{label}</span>}
    </div>
  );
}

/* ---------- Копирование в буфер ---------- */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* ниже резервный путь */ }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export function CopyButton({ text, label = 'Копировать', small = true }: { text: string; label?: string; small?: boolean }) {
  const [done, setDone] = React.useState(false);
  return (
    <button
      className={'btn btn-ghost' + (small ? ' btn-sm' : '')}
      onClick={async () => {
        const ok = await copyText(text);
        setDone(ok);
        toast(ok ? 'Скопировано в буфер обмена' : 'Не удалось скопировать — выделите текст вручную', ok ? 'ok' : 'err');
        setTimeout(() => setDone(false), 2200);
      }}
      aria-label={label}
    >
      {done ? '✓ Скопировано' : '⧉ ' + label}
    </button>
  );
}

/* ---------- Тосты: один регион на всё приложение ---------- */
export interface ToastItem { id: number; text: string; kind: 'ok' | 'err' | 'info' }
type ToastListener = (t: ToastItem) => void;
const listeners = new Set<ToastListener>();
let nextToastId = 0;

export function toast(text: string, kind: ToastItem['kind'] = 'info') {
  const item: ToastItem = { id: ++nextToastId, text, kind };
  listeners.forEach((l) => l(item));
}

export function Toaster() {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  React.useEffect(() => {
    const l: ToastListener = (t) => {
      setItems((prev) => [...prev.slice(-3), t]);
      setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== t.id)), 4200);
    };
    listeners.add(l);
    return () => { listeners.delete(l); };
  }, []);
  return (
    <div className="toast-region" aria-live="polite" aria-atomic="false">
      {items.map((t) => (
        <div key={t.id} className={'toast toast-' + t.kind} role="status">{t.text}</div>
      ))}
    </div>
  );
}
