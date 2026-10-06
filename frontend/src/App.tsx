import React from 'react';
import { Banner } from './components/common';
import { APP_VERSION } from './api/client';
import {
  Dashboard, Chat, ProtocolSearch, DosageCalc, ChecklistPage,
  Templates, Admin, DiffDx, Referral, History, Calculators,
} from './pages/pages';

const LINKS: [string, string][] = [
  ['', 'Дашборд'],
  ['chat', 'Чат'],
  ['protocols', 'Клинические рекомендации'],
  ['dosage', 'Дозировки'],
  ['calc', 'Калькуляторы'],
  ['diff', 'Дифдиагностика'],
  ['referral', 'Госпитализация'],
  ['checklist', 'Чек-лист'],
  ['templates', 'Шаблоны'],
  ['history', 'История'],
  ['admin', 'Админ'],
];

function route() {
  return window.location.hash.replace('#/', '').split('?')[0];
}

function themeInit(): 'light' | 'dark' {
  const saved = localStorage.getItem('lorai-theme');
  if (saved === 'dark' || saved === 'light') return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

class Boundary extends React.Component<{ children: React.ReactNode }, { err: string }> {
  state = { err: '' };
  static getDerivedStateFromError(e: Error) { return { err: e.message }; }
  render() {
    if (this.state.err)
      return (
        <div className="card" role="alert">
          <h2>Что-то пошло не так</h2>
          <p>Экран не смог отобразиться. Обновите страницу — данные на сервере в безопасности.</p>
          <p className="caption">{this.state.err.slice(0, 200)}</p>
          <button className="btn btn-secondary" onClick={() => location.reload()}>Обновить страницу</button>
        </div>
      );
    return this.props.children;
  }
}

function NotFound() {
  return (
    <div className="card notfound" role="alert">
      <div className="nf-code num">404</div>
      <h2>Страница не найдена</h2>
      <p className="muted">Такого раздела в ЛОРАИ нет — возможно, устаревшая ссылка.</p>
      <a className="btn" href="#/" style={{ marginTop: 8 }}>На главную</a>
    </div>
  );
}

function InstallPrompt() {
  const [evt, setEvt] = React.useState<any>(null);
  const [dismissed, setDismissed] = React.useState(() => localStorage.getItem('lorai-install-hide') === '1');
  React.useEffect(() => {
    const visits = Number(localStorage.getItem('lorai-visits') || '0') + 1;
    localStorage.setItem('lorai-visits', String(visits));
    const h = (e: Event) => {
      e.preventDefault();
      if (Number(localStorage.getItem('lorai-visits') || '0') >= 2) setEvt(e);
    };
    window.addEventListener('beforeinstallprompt', h);
    return () => window.removeEventListener('beforeinstallprompt', h);
  }, []);
  if (!evt || dismissed) return null;
  return (
    <div className="banner" role="status">
      <span>📲 Установите ЛОРАИ на главный экран — откроется как отдельное приложение, ранее просмотренные протоколы доступны офлайн.</span>
      <span className="row">
        <button className="btn btn-secondary btn-sm" onClick={() => (evt as any).prompt()}>Установить</button>
        <button className="btn btn-ghost btn-sm" onClick={() => { localStorage.setItem('lorai-install-hide', '1'); setDismissed(true); }}>Позже</button>
      </span>
    </div>
  );
}

export default function App() {
  const [, tick] = React.useState(0);
  const [theme, setTheme] = React.useState<'light' | 'dark'>(themeInit);
  const [online, setOnline] = React.useState(navigator.onLine);
  React.useEffect(() => {
    const f = () => tick((x) => x + 1);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener('hashchange', f);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('hashchange', f);
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  }, []);
  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('lorai-theme', theme);
  }, [theme]);
  const r = route();
  const active = r.split('/')[0];
  React.useEffect(() => {
    const el = document.querySelector<HTMLElement>('.lorai-nav a[aria-current="page"]');
    el?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }, [r]);
  const page =
    r === '' ? <Dashboard /> :
    r === 'chat' ? <Chat /> :
    r.startsWith('protocols') ? <ProtocolSearch /> :
    r === 'dosage' ? <DosageCalc /> :
    r === 'calc' ? <Calculators /> :
    r === 'diff' ? <DiffDx /> :
    r === 'referral' ? <Referral /> :
    r.startsWith('checklist') ? <ChecklistPage /> :
    r === 'templates' ? <Templates /> :
    r === 'history' ? <History /> :
    r === 'admin' ? <Admin /> :
    <NotFound />;
  return (
    <div className="lorai-shell">
      <a href="#main" className="skip-link" onFocus={(e) => (e.currentTarget.style.left = '8px')}>
        Перейти к содержимому
      </a>
      <header className="lorai-header">
        <div className="lorai-brand">
          <span className="lorai-logo" aria-hidden="true">Л</span>
          <div>
            <b>ЛОРАИ</b>
            <span className="caption">Помощник ЛОР-врача · клинические рекомендации</span>
          </div>
        </div>
        <div style={{ marginLeft: 'auto' }} className="row">
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            aria-label={theme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
            title="Тема оформления"
          >
            {theme === 'dark' ? '☀️ Светлая' : '🌙 Тёмная'}
          </button>
        </div>
      </header>
      {!online && (
        <div className="error-box" role="alert" style={{ marginBottom: 12 }}>
          <b>Нет соединения.</b> Проверьте интернет — запросы к серверу сейчас недоступны.
        </div>
      )}
      <Banner />
      <InstallPrompt />
      <nav className="lorai-nav" aria-label="Основные разделы">
        {LINKS.map(([h, l]) => (
          <a key={h} href={'#/' + h} aria-current={(active === h || (h === '' && active === '')) ? 'page' : undefined}>
            {l}
          </a>
        ))}
      </nav>
      <main id="main" className="lorai-main fade-in" key={r} tabIndex={-1}>
        <Boundary>{page}</Boundary>
      </main>
      <footer className="lorai-footer">
        <span>ЛОРАИ v{APP_VERSION} · справочный инструмент, решение принимает врач</span>
        <span>API: {(import.meta as any).env.VITE_API_URL || 'http://localhost:8000'}</span>
      </footer>
    </div>
  );
}
