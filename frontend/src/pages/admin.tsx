import React from 'react';
import { API, api, humanError } from '../api/client';
import { Button, Card, ErrorBox, PageHeader, Skeleton, toast } from '../components/common';
import { clearSession } from '../lib/auth';
import { LoginForm } from './login';
import { confAnyPill, confLabel, toError, useAuth } from './shared';

export function Admin() {
  const session = useAuth();
  const isAdmin = session?.role === 'admin';
  const [docs, setDocs] = React.useState<any[] | null>(null);
  const [filter, setFilter] = React.useState('');
  const [stats, setStats] = React.useState<any>(null);
  const [statsErr, setStatsErr] = React.useState<Error | null>(null);
  const [contra, setContra] = React.useState<any[] | null>(null);
  const [contraErr, setContraErr] = React.useState<Error | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [upResult, setUpResult] = React.useState<any>(null);
  const [upError, setUpError] = React.useState('');
  const [busyDoc, setBusyDoc] = React.useState('');
  const [users, setUsers] = React.useState<any[] | null>(null);
  const [audit, setAudit] = React.useState<any[] | null>(null);
  const [uEmail, setUEmail] = React.useState('');
  const [uPw, setUPw] = React.useState('');
  const [uRole, setURole] = React.useState('doctor');
  const [uBusy, setUBusy] = React.useState(false);

  const loadDocs = React.useCallback(async () => {
    try { setDocs((await api('/admin/documents')).items || []); }
    catch (e) { setDocs([]); toast(humanError(e), 'err'); }
  }, []);

  const loadUsers = React.useCallback(async () => {
    try { setUsers((await api('/admin/users')).items || []); }
    catch (e) { setUsers([]); toast(humanError(e), 'err'); }
  }, []);

  const loadAudit = React.useCallback(async () => {
    try { setAudit((await api('/admin/audit?limit=50')).items || []); }
    catch { setAudit([]); }
  }, []);

  React.useEffect(() => {
    if (isAdmin) { loadDocs(); loadUsers(); loadAudit(); }
  }, [isAdmin, loadDocs, loadUsers, loadAudit]);

  const loadStats = async () => {
    setStatsErr(null);
    try { setStats(await api('/admin/stats')); }
    catch (e) { setStatsErr(toError(e)); }
  };
  const loadContra = async () => {
    setContraErr(null);
    try { setContra((await api('/contradictions')).items || []); }
    catch (e) { setContraErr(toError(e)); }
  };

  /** Разбор PDF идёт в фоне (ответ 202 + status=processing): опрашиваем
      документ, пока статус не сменится. Раньше запрос висел всё время разбора. */
  const pollDocument = async (id: string) => {
    for (let i = 0; i < 120; i += 1) {
      await new Promise((res) => setTimeout(res, 1000));
      try {
        const d = await api('/protocols/' + id);
        if (d && d.status && d.status !== 'processing') return d;
      } catch {
        // документ ещё не создан/недоступен — продолжаем ждать
      }
    }
    return null;
  };

  const upload = async (f: File) => {
    setUploading(true); setUpError(''); setUpResult(null);
    try {
      const fd = new FormData();
      fd.append('f', f);
      const t = localStorage.getItem('token');
      const r = await fetch(API + '/admin/upload', { method: 'POST', headers: { Authorization: 'Bearer ' + t }, body: fd });
      const text = await r.text();
      if (!r.ok) throw new Error(text || ('Ошибка ' + r.status));
      const j = JSON.parse(text);
      setUpResult({ ...j, processing_status: j.status || 'processing' });
      const done = j.document_id ? await pollDocument(j.document_id) : null;
      if (done) {
        setUpResult({ ...j, ...done, processing_status: done.status, icd10: done.icd10_codes || [] });
        toast(
          done.status === 'failed'
            ? 'Не удалось разобрать файл — документ помечен как ошибочный'
            : 'Документ обработан и добавлен в базу',
          done.status === 'failed' ? 'err' : 'ok',
        );
      } else {
        toast('Файл принят, разбор продолжается в фоне', 'info');
      }
      await loadDocs();
    } catch (e) {
      setUpError(e instanceof Error && e.message ? e.message.slice(0, 300) : humanError(e));
    }
    setUploading(false);
  };

  const markReviewed = async (docId: string) => {
    setBusyDoc(docId);
    try {
      await api('/admin/documents/' + docId, { method: 'PATCH', body: JSON.stringify({ needs_review: false }) });
      setDocs((d) => (d || []).map((x) => (x.document_id === docId ? { ...x, needs_review: false } : x)));
      toast('Отмечено как проверенное', 'ok');
    } catch (e) { toast(humanError(e), 'err'); }
    setBusyDoc('');
  };

  /** Учётки теперь в БД: создать врача можно без правки .env и рестарта. */
  const createUser = async () => {
    if (!uEmail.trim() || uPw.length < 8) {
      toast('Укажите email и пароль не короче 8 символов', 'err');
      return;
    }
    setUBusy(true);
    try {
      await api('/admin/users', {
        method: 'POST',
        body: JSON.stringify({ email: uEmail.trim(), password: uPw, role: uRole }),
      });
      toast('Пользователь создан', 'ok');
      setUEmail(''); setUPw(''); setURole('doctor');
      loadUsers(); loadAudit();
    } catch (e) { toast(humanError(e), 'err'); }
    setUBusy(false);
  };

  const patchUser = async (email: string, patch: any) => {
    try {
      await api('/admin/users/' + encodeURIComponent(email), {
        method: 'PATCH', body: JSON.stringify(patch),
      });
      loadUsers(); loadAudit();
      toast('Сохранено', 'ok');
    } catch (e) { toast(humanError(e), 'err'); }
  };

  const changePassword = async (email: string) => {
    const pw = window.prompt('Новый пароль для ' + email + ' (не короче 8 символов)');
    if (pw) await patchUser(email, { password: pw });
  };

  if (!isAdmin) {
    return (
      <div className="stagger">
        <PageHeader
          id="admin-title"
          title="Админ-панель"
          sub={session ? 'Нужны права администратора — этот аккаунт их не имеет.' : 'Войдите под учётной записью администратора клиники.'}
        />
        <Card labelledBy="admin-title">
          {session && (
            <div className="error-box" role="alert" style={{ marginBottom: 12 }}>
              Аккаунт <b>{session.email}</b> имеет роль «врач». Загрузка протоколов и статистика доступны администратору.
              <div className="row" style={{ marginTop: 8 }}>
                <Button variant="secondary" onClick={() => { clearSession(); toast('Вы вышли из системы', 'info'); }}>Сменить пользователя</Button>
              </div>
            </div>
          )}
          <LoginForm
            compact
            onDone={() => { loadDocs(); }}
          />
          <p className="caption" style={{ marginTop: 12 }}>
            Доступы выдаёт администратор клиники в разделе «Пользователи». Первый администратор создаётся из
            <code> .env</code> (ADMIN_EMAIL / ADMIN_PASSWORD) при первом запуске — смените пароль по умолчанию перед пилотом.
          </p>
        </Card>
      </div>
    );
  }

  const list = docs || [];
  const shown = filter.trim()
    ? list.filter((d) => (String(d.nosology) + ' ' + String(d.title) + ' ' + (d.icd10_codes || []).join(' ')).toLowerCase().includes(filter.trim().toLowerCase()))
    : list;
  const needReview = list.filter((d) => d.needs_review).length;

  return (
    <div className="stagger">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <PageHeader id="admin-title" title="Админ-панель" sub={`${session?.email} · администратор`} />
        <Button variant="ghost" onClick={() => { clearSession(); toast('Вы вышли из системы', 'info'); }}>Выйти</Button>
      </div>

      <Card labelledBy="admin-upload">
        <h3 id="admin-upload" style={{ marginTop: 0 }}>Загрузка клинической рекомендации</h3>
        <label className="btn btn-secondary file-btn">
          Загрузить PDF или TXT
          <input type="file" accept=".pdf,.txt" disabled={uploading} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        </label>
        <span className="muted" style={{ marginLeft: 12 }}>до 50 МБ · извлекаются текст, разделы, коды МКБ; повторная загрузка обновляет документ</span>

        {uploading && <Skeleton lines={2} label="Обрабатываю файл: текст, разделы, МКБ" />}        {upError && (
          <div className="error-box" role="alert" style={{ marginTop: 12 }}>
            <b>Не удалось обработать файл.</b> {upError}
            <div className="caption">Проверьте формат (PDF/TXT до 50 МБ) и повторите.</div>
          </div>
        )}
        {upResult && (
          <div className={`panel ${upResult.processing_status === 'failed' ? 'panel-warn' : 'panel-ok'}`}
               style={{ marginTop: 12 }} role="status">
            {upResult.processing_status === 'processing' ? (
              <><b>Принят:</b> {upResult.title} · идёт разбор в фоне</>
            ) : upResult.processing_status === 'failed' ? (
              <><b>Не удалось разобрать:</b> {upResult.title} · документ помечен как ошибочный, загрузите другой файл</>
            ) : (
              <>
                <b>Готово:</b> {upResult.nosology || upResult.title} [{(upResult.icd10 || []).join(', ')}] · статус {upResult.processing_status} · уверенность {upResult.confidence}
                {upResult.duplicate ? ' · обновлён существующий документ' : ''}
                {upResult.needs_review ? ' · требуется ручная проверка (низкая уверенность)' : ''}
              </>
            )}
            {upResult.processing_status !== 'processing' && (
              <p style={{ margin: '8px 0 0' }}><a href="#/protocols">Проверить в поиске</a></p>
            )}
          </div>
        )}
      </Card>

      <Card labelledBy="admin-docs">
        <h3 id="admin-docs" style={{ marginTop: 0 }}>Документы ({list.length}){needReview > 0 ? ` · на проверку: ${needReview}` : ''}</h3>
        {docs === null && <Skeleton lines={4} label="Загружаю список документов" />}
        {docs !== null && list.length === 0 && <p className="muted">В базе пока нет документов.</p>}
        {list.length > 0 && (
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Фильтр по нозологии, файлу или МКБ"
            aria-label="Фильтр документов"
            style={{ marginBottom: 8 }}
          />
        )}
        {shown.map((d: any) => (
          <div key={d.document_id} className="doc-row">
            <b>{d.nosology}</b>
            {(d.icd10_codes || []).map((c: string) => <span key={c} className="icd">{c}</span>)}
            <span className={confAnyPill(d.confidence)}>conf {confLabel(d.confidence)}</span>
            {d.status === 'processing'
              ? <span className="pill pill-warn">обрабатывается</span>
              : d.needs_review
                ? <span className="pill pill-warn">на проверке</span>
                : <span className="pill pill-ok">проверен</span>}
            {d.needs_review && d.status !== 'processing' && (
              <Button variant="ghost" loading={busyDoc === d.document_id} onClick={() => markReviewed(d.document_id)}>Отметить проверенным</Button>
            )}
            <a className="btn btn-sm btn-secondary" href={'#/checklist/' + d.document_id}>Чек-лист</a>
          </div>
        ))}
        {filter && shown.length === 0 && <p className="muted">По фильтру ничего не найдено.</p>}
      </Card>

      <Card labelledBy="admin-stats">
        <h3 id="admin-stats" style={{ marginTop: 0 }}>Аналитика использования</h3>
        <Button variant="secondary" onClick={loadStats}>Обновить статистику</Button>
        {statsErr && <ErrorBox error={statsErr} onRetry={loadStats} />}
        {stats && (
          <div className="stats-grid" style={{ marginTop: 12 }}>
            <div className="stat"><span className="stat-v num">{stats.documents}</span><span className="stat-l">документов в базе</span></div>
            <div className="stat"><span className="stat-v num">{stats.queries_total}</span><span className="stat-l">запросов всего</span></div>
            <div className="stat"><span className="stat-v num">{((stats.refusal_rate ?? 0) * 100).toFixed(1)}%</span><span className="stat-l">отказов: {stats.queries_refused}</span></div>
            <div className="stat"><span className="stat-v num">👍 {stats.feedback?.up} / 👎 {stats.feedback?.down}</span><span className="stat-l">оценки ответов</span></div>
            <div className="stat"><span className="stat-v num">{stats.avg_latency_ms ?? '—'}</span><span className="stat-l">мс — среднее время ответа</span></div>
            <div className="stat"><span className="stat-v num">{stats.cache?.hits}/{(stats.cache?.hits ?? 0) + (stats.cache?.misses ?? 0)}</span><span className="stat-l">кэш: попаданий / запросов</span></div>
          </div>
        )}
        {stats?.knowledge_gaps?.length > 0 && (
          <div className="panel panel-warn" style={{ marginTop: 12 }}>
            <b>Пробелы базы знаний</b> (частые «нет данных» — сигнал догрузить КР):
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {stats.knowledge_gaps.map((g: any, i: number) => <li key={i}>{g.query} — {g.count} раз(а)</li>)}
            </ul>
          </div>
        )}
        {stats && !stats.knowledge_gaps?.length && <p className="muted">Пробелов в базе не зафиксировано.</p>}
      </Card>

      <Card labelledBy="admin-users">
        <h3 id="admin-users" style={{ marginTop: 0 }}>Пользователи и журнал действий</h3>
        <p className="muted" style={{ marginTop: 0 }}>
          Учётные записи хранятся в базе: новый врач появляется сразу, без правки <code>.env</code> и перезапуска.
          Отключение действует немедленно — выданный ранее токен перестаёт работать.
        </p>

        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className="caption">Email</span>
            <input value={uEmail} onChange={(e) => setUEmail(e.target.value)} placeholder="doctor@clinic.ru" aria-label="Email нового пользователя" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className="caption">Пароль</span>
            <input type="password" value={uPw} onChange={(e) => setUPw(e.target.value)} placeholder="не короче 8 символов" aria-label="Пароль нового пользователя" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <span className="caption">Роль</span>
            <select value={uRole} onChange={(e) => setURole(e.target.value)} aria-label="Роль нового пользователя">
              <option value="doctor">врач</option>
              <option value="admin">администратор</option>
            </select>
          </label>
          <Button loading={uBusy} onClick={createUser}>Создать</Button>
        </div>

        {users === null && <Skeleton lines={3} label="Загружаю пользователей" />}
        {(users || []).map((u: any) => (
          <div key={u.email} className="doc-row">
            <b>{u.email}</b>
            {u.full_name ? <span className="muted">{u.full_name}</span> : null}
            <span className={u.role === 'admin' ? 'pill pill-ok' : 'pill'}>{u.role === 'admin' ? 'админ' : 'врач'}</span>
            {!u.active && <span className="pill pill-warn">отключён</span>}
            <span className="caption">
              {u.last_login_at ? `вход: ${String(u.last_login_at).slice(0, 16)}` : 'ещё не входил'}
            </span>
            <Button variant="ghost" onClick={() => patchUser(u.email, { role: u.role === 'admin' ? 'doctor' : 'admin' })}>
              {u.role === 'admin' ? 'Сделать врачом' : 'Сделать админом'}
            </Button>
            <Button variant="ghost" onClick={() => patchUser(u.email, { active: !u.active })}>
              {u.active ? 'Отключить' : 'Включить'}
            </Button>
            <Button variant="ghost" onClick={() => changePassword(u.email)}>Пароль</Button>
          </div>
        ))}

        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <h4 style={{ margin: 0 }}>Журнал действий</h4>
          <Button variant="secondary" onClick={loadAudit}>Обновить</Button>
        </div>
        {audit === null && <Skeleton lines={3} label="Загружаю журнал" />}
        {audit !== null && audit.length === 0 && <p className="muted">Записей пока нет.</p>}
        {audit !== null && audit.length > 0 && (
          <div style={{ maxHeight: 260, overflowY: 'auto', marginTop: 8 }}>
            {(audit || []).map((a: any) => (
              <div key={a.id} className="caption" style={{ padding: '4px 0', borderBottom: '1px solid var(--line, #eee)' }}>
                <span className="muted">{String(a.at).slice(0, 16)}</span>{' · '}
                <b>{a.user}</b>{' · '}{a.action}
                {a.target ? ` · ${a.target}` : ''}
                {a.detail ? <span className="muted"> · {a.detail}</span> : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card labelledBy="admin-contra">
        <h3 id="admin-contra" style={{ marginTop: 0 }}>Противоречия в базе</h3>
        <Button variant="secondary" onClick={loadContra}>Проверить противоречия</Button>
        {contraErr && <ErrorBox error={contraErr} onRetry={loadContra} />}
        {contra === null && !contraErr && <p className="muted" style={{ marginTop: 10 }}>Проверка не запускалась.</p>}
        {contra !== null && contra.length === 0 && <p className="muted" style={{ marginTop: 10 }}>Противоречий не найдено.</p>}
        {(contra || []).map((x: any, i: number) => (
          <div key={i} className="panel panel-warn" style={{ marginTop: 10 }}>
            <b>{x.doc_a?.title}</b> ↔ <b>{x.doc_b?.title}</b> (общие МКБ: {(x.shared_icd || []).join(', ')})
            <p className="muted" style={{ margin: '6px 0 0' }}>
              Только в первом: {(x.only_in_a || []).join(', ') || '—'}; только во втором: {(x.only_in_b || []).join(', ') || '—'}
            </p>
            <i>{x.note}</i>
          </div>
        ))}
      </Card>
    </div>
  );
}
