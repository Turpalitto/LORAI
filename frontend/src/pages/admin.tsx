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

  const loadDocs = React.useCallback(async () => {
    try { setDocs((await api('/admin/documents')).items || []); }
    catch (e) { setDocs([]); toast(humanError(e), 'err'); }
  }, []);

  React.useEffect(() => { if (isAdmin) loadDocs(); }, [isAdmin, loadDocs]);

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
      setUpResult(j);
      await loadDocs();
      toast('Документ обработан и добавлен в базу', 'ok');
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
            Доступы администратора задаются в <code>.env</code> (ADMIN_EMAIL / ADMIN_PASSWORD). Смените пароль по умолчанию перед пилотом.
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

        {uploading && <Skeleton lines={2} label="Обрабатываю файл: текст, разделы, МКБ" />}
        {upError && (
          <div className="error-box" role="alert" style={{ marginTop: 12 }}>
            <b>Не удалось обработать файл.</b> {upError}
            <div className="caption">Проверьте формат (PDF/TXT до 50 МБ) и повторите.</div>
          </div>
        )}
        {upResult && (
          <div className="panel panel-ok" style={{ marginTop: 12 }} role="status">
            <b>Готово:</b> {upResult.nosology || upResult.title} [{(upResult.icd10 || []).join(', ')}] · статус {upResult.processing_status} · уверенность {upResult.confidence}
            {upResult.duplicate ? ' · обновлён существующий документ' : ''}
            {upResult.needs_review ? ' · требуется ручная проверка (низкая уверенность)' : ''}
            <p style={{ margin: '8px 0 0' }}><a href="#/protocols">Проверить в поиске</a></p>
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
            {d.needs_review
              ? <span className="pill pill-warn">на проверке</span>
              : <span className="pill pill-ok">проверен</span>}
            {d.needs_review && (
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
