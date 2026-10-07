import React from 'react';
import { Banner, Button, Skeleton, Toaster, toast } from './components/common';
import { APP_VERSION } from './api/client';
import { clearSession, expiresInText, readSession, roleLabel, type Session } from './lib/auth';
import { onAuthChange } from './lib/auth';

/* Маршруты грузятся по требованию: первый экран (дашборд) не тянет за собой
   админку, шаблоны и калькуляторы — бандл делится на чанки. */
const Dashboard = React.lazy(() => import('./pages/dashboard').then((m) => ({ default: m.Dashboard })));
const Chat = React.lazy(() => import('./pages/chat').then((m) => ({ default: m.Chat })));
const ProtocolSearch = React.lazy(() => import('./pages/protocols').then((m) => ({ default: m.ProtocolSearch })));
const ChecklistPage = React.lazy(() => import('./pages/checklist').then((m) => ({ default: m.ChecklistPage })));
const DosageCalc = React.lazy(() => import('./pages/tools').then((m) => ({ default: m.DosageCalc })));
const Calculators = React.lazy(() => import('./pages/tools').then((m) => ({ default: m.Calculators })));
const DiffDx = React.lazy(() => import('./pages/tools').then((m) => ({ default: m.DiffDx })));
const Referral = React.lazy(() => import('./pages/tools').then((m) => ({ default: m.Referral })));
const Templates = React.lazy(() => import('./pages/tools').then((m) => ({ default: m.Templates })));
const History = React.lazy(() => import('./pages/history').then((m) => ({ default: m.History })));
const Admin = React.lazy(() => import('./pages/admin').then((m) => ({ default: m.Admin })));
const Login = React.lazy(() => import('./pages/login').then((m) => ({ default: m.Login })));

const NAV: [string, string][] = [
  ['', 'Дашборд'],
  ['chat', 'Чат'],
  ['protocols', 'Протоколы'],
  ['dosage', 'Дозировки'],
  ['calc', 'Калькуляторы'],
  ['diff', 'Дифдиагностика'],
  ['referral', 'Госпитализация'],
  ['checklist', 'Чек-лист'],
  ['templates', 'Шаблоны'],
  ['history', 'История'],
  ['admin', 'Админ'],
];

const TITLES: Record<string, string> = {
  '': 'Дашборд',
  chat: 'Чат-ассистент',
  protocols: 'Клинические рекомендации',
  dosage: 'Калькулятор дозировок',
  calc: 'Клинические калькуляторы',
  diff: 'Дифференциальная диагностика',
  referral: 'Направление и госпитализация',
  checklist: 'Чек-лист приёма',
  templates: 'Шаблоны заключений',
  history: 'История запросов',
  admin: 'Админ-панель',
  login: 'Вход',
};

function route() {
  return window.location.hash.replace(/^#\/?/, '').split('?')[0];
}

function themeInit(): 'light' | 'dark' {
  const saved = localStorage.getItem('lorai-theme');
  if (saved === 'dark' || saved === 'light') return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

class Boundary extends React.Component<{ children: React.ReactNode; resetKey?: string }, { err: string }> {
  state = { err: '' };
  static getDerivedStateFromError(e: Error) { return { err: e.message }; }
  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.err) this.setState({ err: '' });
  }
  render() {
    if (this.state.err)
      return (
        <div className="card" role="alert">
          <h2>Что-то пошло не так</h2>
          <p>Экран не смог отобразиться. Обновите страницу — данные на сервере в безопасности.</p>
          <p className="caption">{this.state.err.slice(0, 200)}</p>
          <Button variant="secondary" onClick={() => location.reload()}>Обновить страницу</Button>
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
      <div className="quick-links" style={{ justifyContent: 'center', marginTop: 12 }}>
        <a href="#/">На дашборд</a>
        <a href="#/chat">В чат</a>
        <a href="#/protocols">К протоколам</a>
      </div>
    </div>
  );
}

interface InstallEvent extends Event { prompt: () => Promise<void> }

function InstallPrompt() {
  const [evt, setEvt] = React.useState<InstallEvent | null>(null);
  const [dismissed, setDismissed] = React.useState(() => localStorage.getItem('lorai-install-hide') === '1');
  React.useEffect(() => {
    const visits = Number(localStorage.getItem('lorai-visits') || '0') + 1;
    localStorage.setItem('lorai-visits', String(visits));
    const h = (e: Event) => {
      e.preventDefault();
      if (Number(localStorage.getItem('lorai-visits') || '0') >= 2) setEvt(e as InstallEvent);
    };
    window.addEventListener('beforeinstallprompt', h);
    return () => window.removeEventListener('beforeinstallprompt', h);
  }, []);
  if (!evt || dismissed) return null;
  const hide = () => { localStorage.setItem('lorai-install-hide', '1'); setDismissed(true); };
  return (
    <div className="banner" role="status">
      <span>📲 Установите ЛОРАИ на главный экран — приложение откроется отдельно, а просмотренные протоколы будут доступны офлайн.</span>
      <span className="row">
        <Button variant="secondary" onClick={() => { evt.prompt(); hide(); }}>Установить</Button>
        <Button variant="ghost" onClick={hide}>Позже</Button>
      </span>
    </div>
  );
}

function SessionChip({ session }: { session: Session }) {
  const [open, setOpen] = React.useState(false);
  const left = expiresInText(session.exp);
  return (
    <div className="session-chip">
      <button className="btn btn-ghost btn-sm" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="true">
        <span className="session-dot" aria-hidden="true" />
        {session.role === 'admin' ? 'админ' : 'врач'}
      </button>
      {open && (
        <div className="session-menu" role="menu">
          <div className="session-who">
            <b>{session.email || 'сессия'}</b>
            <span className="caption">{roleLabel(session.role)}{left ? ' · ' + left : ''}</span>
          </div>
          <a href="#/history" role="menuitem" onClick={() => setOpen(false)}>История запросов</a>
          <a href="#/protocols" role="menuitem" onClick={() => setOpen(false)}>Избранное</a>
          {session.role === 'admin' && <a href="#/admin" role="menuitem" onClick={() => setOpen(false)}>Админ-панель</a>}
          <button className="session-out" role="menuitem" onClick={() => { clearSession(); setOpen(false); toast('Вы вышли из системы', 'info'); }}>
            Выйти
          </button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [, tick] = React.useState(0);
  const [theme, setTheme] = React.useState<'light' | 'dark'>(themeInit);
  const [online, setOnline] = React.useState(navigator.onLine);
  const [session, setSession] = React.useState<Session | null>(() => readSession());
  const mainRef = React.useRef<HTMLElement | null>(null);
  const firstRender = React.useRef(true);

  React.useEffect(() => {
    const f = () => tick((x) => x + 1);
    const on = () => { setOnline(true); toast('Соединение восстановлено', 'ok'); };
    const off = () => setOnline(false);
    const auth = () => setSession(readSession());
    window.addEventListener('hashchange', f);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    const unsub = onAuthChange(auth);
    return () => {
      window.removeEventListener('hashchange', f);
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
      unsub();
    };
  }, []);

  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('lorai-theme', theme);
  }, [theme]);

  const r = route();
  const active = r.split('/')[0];

  /* Заголовок вкладки и перевод фокуса на содержимое при смене раздела
     (скринридер и клавиатура не «застревают» в навигации). */
  React.useEffect(() => {
    const name = TITLES[active] || 'Раздел';
    document.title = `${name} · ЛОРАИ — помощник ЛОР-врача`;
    if (firstRender.current) { firstRender.current = false; return; }
    mainRef.current?.focus();
  }, [active, r]);

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
    r === 'login' ? <Login /> :
    <NotFound />;

  return (
    <div className="lorai-shell">
      <a href="#main" className="skip-link">Перейти к содержимому</a>
      <header className="lorai-header">
        <div className="lorai-brand">
          <span className="lorai-logo" aria-hidden="true">Л</span>
          <div>
            <b>ЛОРАИ</b>
            <span className="caption">Помощник ЛОР-врача · клинические рекомендации</span>
          </div>
        </div>
        <div className="header-actions">
          <Button
            variant="ghost"
            onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
            aria-label={theme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
            title="Тема оформления"
          >
            {theme === 'dark' ? '☀️ Светлая' : '🌙 Тёмная'}
          </Button>
          {session
            ? <SessionChip session={session} />
            : <a className="btn btn-ghost btn-sm" href="#/login">Войти</a>}
        </div>
      </header>

      {!online && (
        <div className="error-box" role="alert" style={{ marginBottom: 12 }}>
          <b>Нет соединения.</b> Ранее открытые протоколы доступны офлайн, запросы к серверу — нет.
        </div>
      )}
      <Banner />
      <InstallPrompt />

      <nav className="lorai-nav" aria-label="Основные разделы">
        {NAV.map(([h, l]) => (
          <a key={h} href={'#/' + h} aria-current={active === h ? 'page' : undefined}>{l}</a>
        ))}
      </nav>

      <main id="main" className="lorai-main fade-in" key={r} tabIndex={-1} ref={mainRef}>
        <Boundary resetKey={r}>
          <React.Suspense fallback={<div className="card"><Skeleton lines={4} label="Открываю раздел" /></div>}>
            {page}
          </React.Suspense>
        </Boundary>
      </main>

      <footer className="lorai-footer">
        <span>ЛОРАИ v{APP_VERSION} · справочный инструмент, решение принимает врач</span>
        <span>API: {(import.meta as any).env.VITE_API_URL || 'http://localhost:8000'}</span>
      </footer>
      <Toaster />
    </div>
  );
}
