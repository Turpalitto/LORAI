import React from 'react';
import { DISC, api, humanError } from '../api/client';

export function Banner() {
  return (
    <div className="banner" role="note" aria-label="Предупреждение о персональных данных">
      ⚠️ {DISC}
    </div>
  );
}

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

export function Card({ children, labelledBy }: { children: React.ReactNode; labelledBy?: string }) {
  return (
    <section className="card" aria-labelledby={labelledBy}>
      {children}
    </section>
  );
}

export function PageHeader({ title, sub, id }: { title: string; sub?: string; id: string }) {
  return (
    <div>
      <h2 id={id}>{title}</h2>
      {sub && <p className="caption" style={{ marginTop: -8 }}>{sub}</p>}
    </div>
  );
}

export function Skeleton({ lines = 3, label = 'Загрузка данных' }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} style={{ display: 'grid', gap: 8, marginTop: 12 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 22 : 16, opacity: 1 - i * 0.12 }} />
      ))}
      <span className="caption">{label}…</span>
    </div>
  );
}

export function Empty({ title, hint, action }: { title: string; hint: string; action?: React.ReactNode }) {
  return (
    <div className="empty" role="status">
      <b>{title}</b>
      <div style={{ fontSize: 14 }}>{hint}</div>
      {action && <div className="row" style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="error-box" role="alert" style={{ marginTop: 12 }}>
      <b>Не получилось.</b> {humanError(error)}
      {onRetry && (
        <div className="row" style={{ marginTop: 8 }}>
          <Button variant="secondary" onClick={onRetry}>Повторить</Button>
        </div>
      )}
    </div>
  );
}

let toastId = 0;
export function useToasts() {
  const [toasts, setToasts] = React.useState<{ id: number; text: string }[]>([]);
  const push = React.useCallback((text: string) => {
    const id = ++toastId;
    setToasts((t) => [...t, { id, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const region = (
    <div className="toast-region" aria-live="polite" aria-atomic="false">
      {toasts.map((t) => (
        <div key={t.id} className="toast" role="status">{t.text}</div>
      ))}
    </div>
  );
  return { push, region };
}

export function useChat() {
  const [q, setQ] = React.useState('');
  const [a, setA] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<unknown>(null);
  const ask = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api('/chat', { method: 'POST', body: JSON.stringify({ query: q }) });
      setA(r.answer || r.warning || JSON.stringify(r));
    } catch (e) {
      setError(e);
      setA('');
    }
    setLoading(false);
  };
  return { q, setQ, a, ask, loading, error };
}
