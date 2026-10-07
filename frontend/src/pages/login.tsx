import React from 'react';
import { api, humanError, login } from '../api/client';
import { Button, Card, PageHeader, toast } from '../components/common';
import { saveToken } from '../lib/auth';
import { useAuth } from './shared';

/** Общая форма входа: используется и на странице «Вход», и в админ-панели. */
export function LoginForm({ onDone, compact }: { onDone?: () => void; compact?: boolean }) {
  const [email, setEmail] = React.useState('');
  const [pw, setPw] = React.useState('');
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !pw) { setErr('Введите e-mail и пароль.'); return; }
    setBusy(true); setErr('');
    try {
      const r = await login(email.trim(), pw);
      saveToken(r.token);
      toast('Вход выполнен' + (r.role === 'admin' ? ' — права администратора' : ''), 'ok');
      onDone?.();
    } catch (e2) {
      setErr(humanError(e2) === 'Нужна авторизация. Войдите снова — сессия могла закончиться.'
        ? 'Неверный e-mail или пароль.'
        : humanError(e2));
    }
    setBusy(false);
  };

  return (
    <form onSubmit={submit} autoComplete="on">
      <div className={compact ? 'form-line' : 'login-grid'}>
        <label className="field">
          E-mail
          <input
            type="email"
            name="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="doctor@clinic.ru"
            required
          />
        </label>
        <label className="field">
          Пароль
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            required
          />
        </label>
      </div>
      {err && <div className="error-box" role="alert" style={{ marginTop: 10 }}>{err}</div>}
      <div className="row" style={{ marginTop: 12 }}>
        <Button type="submit" loading={busy}>Войти</Button>
      </div>
    </form>
  );
}

export function Login() {
  const session = useAuth();
  const [justIn, setJustIn] = React.useState(false);
  const next = new URLSearchParams(window.location.hash.split('?')[1] || '').get('next');

  if (session || justIn) {
    return (
      <div className="stagger">
        <PageHeader id="login-title" title="Вы вошли" sub={session ? `${session.email} · ${session.role === 'admin' ? 'администратор' : 'врач'}` : undefined} />
        <Card>
          <p>Сессия активна: история запросов, избранное, оценки ответов и админ-панель доступны.</p>
          <div className="quick-links" style={{ marginTop: 12 }}>
            <a href={next || '#/'}>Продолжить работу</a>
            <a href="#/chat">В чат</a>
            <a href="#/history">История</a>
            {session?.role === 'admin' && <a href="#/admin">Админ-панель</a>}
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="stagger">
      <PageHeader id="login-title" title="Вход в ЛОРАИ" sub="Доступ выдаёт администратор клиники. Сессия хранится в этом браузере." />
      <Card labelledBy="login-title">
        <LoginForm onDone={() => setJustIn(true)} />
        <p className="caption" style={{ marginTop: 12 }}>
          Пароль не передаётся третьим лицам и не сохраняется в браузере — хранится только токен сессии.
          Если доступ утерян, обратитесь к администратору клиники.
        </p>
      </Card>
    </div>
  );
}
