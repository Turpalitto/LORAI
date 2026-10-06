import React, { useState } from 'react';
import { API, api } from '../api/client';
import { ArtChat, ArtEmpty, ArtOnboarding, ArtSearch } from '../components/illustrations';
export function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [onb, setOnb] = useState(() => localStorage.getItem('lorai_onb') !== 'done');
  React.useEffect(() => { api('/admin/documents').then(d => setStats({ docs: d.items?.length })).catch(() => api('/protocols?q=').then(d => setStats({ docs: d.items?.length }))); }, []);
  const done = () => { localStorage.setItem('lorai_onb', 'done'); setOnb(false); };
  return <div><h2>Дашборд</h2>
    {onb && <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', padding: 12, borderRadius: 8, marginBottom: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
      <ArtOnboarding />
      <div><b>Добро пожаловать в LORAI</b> — помощник по клиническим рекомендациям (ЛОР).<br />
      1. <b>Чат</b> — задайте клинический вопрос, ответ придёт с цитатами протоколов.<br />
      2. <b>Поиск протокола</b> — точная выдача по нозологии/МКБ без LLM.<br />
      3. <b>Дифдиагностика</b> — ранжирование нозологий по симптомам.<br />
      <button onClick={done} style={{ marginTop: 8 }}>Понятно, скрыть</button>
      </div></div>}
    <p>Документов в базе: {stats?.docs ?? '…'}</p>
    <p style={{ color: '#6b7280', fontSize: 13 }}>Быстрые разделы: <a href="#/chat">чат</a> · <a href="#/search">поиск протокола</a> · <a href="#/diffdx">дифдиагностика</a> · <a href="#/dosage">дозировки</a></p>
  </div>;
}
function confColor(score: number | undefined): [string, string] {
  if ((score ?? 0) >= 0.5) return ['высокая', '#16a34a'];
  if ((score ?? 0) >= 0.2) return ['средняя', '#ca8a04'];
  return ['низкая', '#9ca3af'];
}
export function Chat() {
  const [q, setQ] = React.useState('Острый средний отит: диагностика и лечение?');
  const [a, setA] = React.useState('');
  const [meta, setMeta] = React.useState<any>(null);
  const [sources, setSources] = React.useState<any[]>([]);
  const [sid, setSid] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState('');
  const [voted, setVoted] = React.useState(0);
  const [streaming, setStreaming] = React.useState(false);
  const stopRef = React.useRef(false);
  const askFull = async () => {
    try {
      const r = await api('/chat', { method: 'POST', body: JSON.stringify({ query: q, session_id: sid || undefined }) });
      setA(r.answer || r.warning || '');
      setSources(r.sources || []);
      if (r.session_id) setSid(r.session_id);
      setMeta(r);
    } catch (e) { setErr('Ошибка запроса: ' + (e instanceof Error ? e.message : String(e))); }
  };
  const ask = async () => {
    if (!q.trim()) { setErr('Введите вопрос — пустой запрос отклоняется.'); return; }
    setLoading(true); setErr(''); setVoted(0); setA(''); setSources([]); setMeta(null);
    // Потоковый режим: meta (источники) приходит первым, текст дописывается
    // по мере чанков. При любой ошибке стрима — тихий фолбэк на POST /chat.
    try {
      const ctrl = new AbortController();
      (stopRef as any).current = ctrl;
      const res = await fetch(API + '/chat/stream?query=' + encodeURIComponent(q) + (sid ? '&session_id=' + encodeURIComponent(sid) : ''), { signal: ctrl.signal });
      if (!res.ok || !res.body) throw new Error('stream unavailable');
      setStreaming(true);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '', acc = '';
      const pump = async (): Promise<boolean> => {
        const { done, value } = await reader.read();
        if (done) return true;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop() || '';
        for (const p of parts) {
          const line = p.split('\n').find((l) => l.startsWith('data: '));
          if (!line) continue;
          try {
            const e = JSON.parse(line.slice(6));
            if (e.type === 'meta') {
              setSources(e.sources || []);
              if (e.session_id) setSid(e.session_id);
              setMeta(e);
            } else if (e.type === 'token') {
              acc += e.text || '';
              setA(acc);
            }
          } catch { /* пропуск битого чанка */ }
        }
        return false;
      };
      while (!(await pump())) {
        if ((stopRef as any).stop) { try { await reader.cancel(); } catch { /* noop */ } break; }
      }
      setStreaming(false);
      if (!acc) await askFull();
    } catch {
      setStreaming(false);
      await askFull();
    }
    setLoading(false);
  };
  const vote = async (v: number) => {
    try { await api('/feedback', { method: 'POST', body: JSON.stringify({ query: q, vote: v }) }); setVoted(v); }
    catch { setErr('Оценку сохранить не удалось (нужен вход).'); }
  };
  const [confLabel, confBg] = confColor(meta?.top_score);
  return <div><h2>Чат-ассистент (RAG)</h2><p style={{ background: '#fef3c7', padding: 8, borderRadius: 6 }}>⚠️ Не вводите персональные данные пациента (ФИО, паспорт, телефон, СНИЛС).</p><textarea value={q} onChange={e => setQ(e.target.value)} rows={3} style={{ width: '100%' }} /><br /><button onClick={ask} disabled={loading}>{loading ? (streaming ? 'Получаю ответ…' : 'Думаю…') : 'Спросить'}</button>{streaming && <button onClick={() => { (stopRef as any).stop = true; }} style={{ marginLeft: 8 }}>Остановить</button>}{sid && <span style={{ marginLeft: 8, fontSize: 12, color: '#6b7280' }}>сессия {sid.slice(0, 8)}… (помнит контекст)</span>}
    {loading && !a && <div style={{ marginTop: 8 }}><div style={{ background: '#e5e7eb', borderRadius: 6, height: 14, marginBottom: 6 }} /><div style={{ background: '#e5e7eb', borderRadius: 6, height: 14, width: '70%', marginBottom: 6 }} /><div style={{ background: '#e5e7eb', borderRadius: 6, height: 14, width: '40%' }} /></div>}
    {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
    {!loading && !a && !meta?.needs_clarification && !err && <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 8 }}><ArtChat /><p style={{ color: '#6b7280' }}>Здесь появится ответ с цитатами клинических рекомендаций.</p></div>}
    {meta?.needs_clarification && <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', padding: 10, borderRadius: 6, marginTop: 8 }}><b>Уточните, пожалуйста:</b> {meta.clarifying_question}</div>}
    {a && <div style={{ marginTop: 8 }}>
      <span style={{ background: confBg, color: '#fff', borderRadius: 10, padding: '2px 10px', fontSize: 12 }}>уверенность: {confLabel} (score={meta?.top_score?.toFixed?.(2) ?? meta?.top_score})</span>
      {meta?.cached && <span style={{ marginLeft: 6, fontSize: 12, color: '#6b7280' }}>из кэша · {meta?.latency_ms} мс</span>}
      {meta?.doc_count > 1 && <span style={{ marginLeft: 6, fontSize: 12, color: '#6b7280' }}>синтез из {meta.doc_count} документов</span>}
      <pre style={{ whiteSpace: 'pre-wrap', background: '#f3f4f6', padding: 12 }}>{a}{streaming && <span className="stream-caret" aria-hidden="true" />}</pre>
      <div>Ответ полезен? <button onClick={() => vote(1)} disabled={voted !== 0}>{voted === 1 ? '👍 спасибо!' : '👍'}</button> <button onClick={() => vote(-1)} disabled={voted !== 0}>{voted === -1 ? '👎 принято' : '👎'}</button></div>
    </div>}
    {sources.length > 0 && <details style={{ marginTop: 8 }}><summary>Источники ({sources.length})</summary>{sources.map((s: any, i: number) => <div key={i} style={{ border: '1px solid #ddd', margin: 4, padding: 6 }}>[Документ: {s.document || s.title || s.nosology}, Раздел: {s.section}, Стр.: {Array.isArray(s.page_range) ? s.page_range.join(', ') : s.page_range}] (score={s.score})</div>)}</details>}</div>;
}
export function ProtocolSearch() {
  const [q, setQ] = React.useState('H66'); const [items, setItems] = React.useState<any[]>([]);
  const [rel, setRel] = React.useState<Record<string, any[]>>({});
  const [favs, setFavs] = React.useState<any[]>([]); const [favHint, setFavHint] = React.useState(false);
  const [loading, setLoading] = React.useState(false); const [err, setErr] = React.useState('');
  const go = async () => { setLoading(true); setErr(''); try { const r = await api('/protocols?q=' + encodeURIComponent(q)); setItems(r.items || []); } catch (e) { setErr('Поиск недоступен: ' + (e instanceof Error ? e.message : String(e))); } setLoading(false); };
  const showRelated = async (id: string) => {
    if (rel[id]) { const c = { ...rel }; delete c[id]; setRel(c); return; }
    try { const r = await api('/protocols/' + id + '/related'); setRel({ ...rel, [id]: r.items || [] }); }
    catch { setErr('Не удалось загрузить похожие протоколы.'); }
  };
  const loadFavs = async () => { try { setFavs((await api('/favorites')).items || []); } catch { setFavHint(true); } };
  const addFav = async (doc_id: string) => {
    try { await api('/favorites', { method: 'POST', body: JSON.stringify({ doc_id }) }); await loadFavs(); }
    catch { setErr('Избранное требует входа (войдите в разделе «Админ» — токен сохранится).'); }
  };
  const delFav = async (id: number) => { try { await api('/favorites/' + id, { method: 'DELETE' }); await loadFavs(); } catch { setErr('Не удалось удалить из избранного.'); } };
  React.useEffect(() => { go(); loadFavs(); }, []);
  return <div><h2>Поиск протокола</h2><input value={q} onChange={e => setQ(e.target.value)} /><button onClick={go} disabled={loading}>{loading ? '…' : 'Найти'}</button>
    {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
    {!loading && items.length === 0 && !err && <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}><ArtSearch /><p style={{ color: '#6b7280' }}>Ничего не найдено. Попробуйте код МКБ (например, H66) или другое название. Точный поиск работает и без чата.</p></div>}
    {items.map((p: any) => <div key={p.document_id} style={{ border: '1px solid #ddd', margin: 6, padding: 6 }}><b>{p.nosology}</b> [{(p.icd10_codes || []).join(', ')}] <a href={'#/checklist/' + p.document_id}>чек-лист</a> <button onClick={() => showRelated(p.document_id)} style={{ marginLeft: 6 }}>{rel[p.document_id] ? 'скрыть похожие' : 'похожие'}</button> <button onClick={() => addFav(p.document_id)} title="В избранное" style={{ marginLeft: 6 }}>⭐</button>
      {rel[p.document_id] && (rel[p.document_id].length === 0 ? <p style={{ color: '#6b7280' }}>Похожих протоколов не найдено.</p> : <ul>{rel[p.document_id].map((r: any) => <li key={r.document_id}>{r.nosology} [{(r.icd10_codes || []).join(', ')}] — {(r.reasons || []).join('; ')}</li>)}</ul>)}
    </div>)}
    <h3>⭐ Моё избранное</h3>
    {favHint && favs.length === 0 && <p style={{ color: '#6b7280' }}>Войдите в разделе «Админ», чтобы сохранять избранные протоколы.</p>}
    {favs.map((f: any) => <div key={f.id} style={{ borderBottom: '1px solid #eee', padding: 4 }}>{f.doc_id} {f.note && <i>({f.note})</i>} <button onClick={() => delFav(f.id)}>✕</button></div>)}</div>;
}
export function DosageCalc() {
  const [w, setW] = React.useState('20'); const [m, setM] = React.useState('40'); const [r, setR] = React.useState<any>(null);
  const go = async () => setR(await api('/dosage', { method: 'POST', body: JSON.stringify({ weight_kg: +w, mg_per_kg: +m }) }));
  return <div><h2>Калькулятор дозировок</h2>Вес (кг): <input value={w} onChange={e => setW(e.target.value)} /> мг/кг: <input value={m} onChange={e => setM(e.target.value)} /> <button onClick={go}>Рассчитать</button>{r && <p>Разовая доза: <b>{r.single_dose_mg} мг</b>. {r.warning}</p>}</div>;
}
export function Calculators() {
  const [fever, setFever] = React.useState(false); const [exudate, setExudate] = React.useState(false);
  const [nodes, setNodes] = React.useState(false); const [noCough, setNoCough] = React.useState(false);
  const [age, setAge] = React.useState('15-44'); const [centor, setCentor] = React.useState<any>(null);
  const [pta, setPta] = React.useState(['20', '20', '25', '15']); const [ptaR, setPtaR] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  const goCentor = async () => { setErr(''); try { setCentor(await api('/calculators/centor', { method: 'POST', body: JSON.stringify({ fever, exudate, nodes, no_cough: noCough, age_band: age }) })); } catch (e) { setErr('Ошибка Centor: ' + (e instanceof Error ? e.message : String(e))); } };
  const goPta = async () => { setErr(''); try { setPtaR(await api('/calculators/pta', { method: 'POST', body: JSON.stringify({ thresholds_db: pta.map(Number) }) })); } catch (e) { setErr('Ошибка PTA: ' + (e instanceof Error ? e.message : String(e))); } };
  return <div><h2>Клинические калькуляторы</h2><p style={{ color: '#6b7280' }}>Чистые формулы по опубликованным шкалам, без ИИ. Решение всегда за врачом.</p>
    {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
    <h3>Шкала Centor/McIsaac (фарингит)</h3>
    <label><input type="checkbox" checked={fever} onChange={e => setFever(e.target.checked)} /> Температура ≥38°C</label><br />
    <label><input type="checkbox" checked={exudate} onChange={e => setExudate(e.target.checked)} /> Налёт/экссудат на миндалинах</label><br />
    <label><input type="checkbox" checked={nodes} onChange={e => setNodes(e.target.checked)} /> Болезненные шейные лимфоузлы</label><br />
    <label><input type="checkbox" checked={noCough} onChange={e => setNoCough(e.target.checked)} /> Кашля нет</label><br />
    Возраст: <select value={age} onChange={e => setAge(e.target.value)}><option value="3-14">3–14</option><option value="15-44">15–44</option><option value="45+">45+</option></select> <button onClick={goCentor}>Посчитать</button>
    {centor && <p>Баллов: <b>{centor.score} из {centor.max}</b> — {centor.interpretation}. {centor.recommendation}</p>}
    <h3>Средний порог слуха PTA (0.5/1/2/4 кГц, дБ)</h3>
    {pta.map((v, i) => <span key={i}><input value={v} onChange={e => { const c = [...pta]; c[i] = e.target.value; setPta(c); }} style={{ width: 60 }} /> </span>)} <button onClick={goPta}>Посчитать</button>
    {ptaR && <p>Среднее: <b>{ptaR.average_db} дБ</b> — {ptaR.grade}. {ptaR.recommendation}</p>}</div>;
}
export function ChecklistPage() {
  const id = window.location.hash.split('/')[2] || '';
  const [c, setC] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  React.useEffect(() => { if (id) api('/checklist/' + id).then(setC).catch(() => setErr('Чек-лист недоступен: нет соединения с сервером.')); }, [id]);
  if (!id) return <div><h2>Чек-лист приёма</h2><div style={{ display: 'flex', gap: 12, alignItems: 'center' }}><ArtEmpty /><p style={{ color: '#6b7280' }}>Откройте чек-лист из поиска протокола — там кнопка «чек-лист» у каждой нозологии.</p></div></div>;
  return <div><style>{'@media print { button { display: none; } body { font-size: 12pt; } }'}</style><h2>Чек-лист приёма: {c?.nosology ?? '…'}</h2>
  {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
  {!c && !err && <p style={{ color: '#6b7280' }}>Загрузка чек-листа…</p>}
  {(c?.checklist || []).map((b: any, i: number) => <div key={i}><h4>{b.block}</h4><ul>{b.points.map((p: string, j: number) => <li key={j}><label><input type="checkbox" /> {p}</label></li>)}</ul></div>)}<button onClick={() => window.print()}>Печать / PDF</button></div>;
}
export function DiffDx() {
  const [s, setS] = React.useState('оталгия, лихорадка'); const [r, setR] = React.useState<any[]>([]);
  const [why, setWhy] = React.useState(''); const [expl, setExpl] = React.useState('');
  const [flags, setFlags] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(false); const [err, setErr] = React.useState('');
  const go = async () => {
    setLoading(true); setErr('');
    try {
      const j = await api('/diff-diagnosis', { method: 'POST', body: JSON.stringify({ symptoms: s.split(/[,\n]/).map(x => x.trim()).filter(Boolean) }) });
      const ranked = j.ranked || []; setR(ranked);
      setWhy(ranked[0]?.why_first || ''); setExpl(ranked[0]?.explanation || '');
      setFlags(j.red_flags || []);
    } catch (e) { setErr('Ошибка: ' + (e instanceof Error ? e.message : String(e))); }
    setLoading(false);
  };
  return <div><h2>Дифференциальная диагностика</h2>Симптомы (через запятую): <input value={s} onChange={e => setS(e.target.value)} style={{ width: '60%' }} /> <button onClick={go} disabled={loading}>{loading ? '…' : 'Ранжировать'}</button>
    {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
    {flags.length > 0 && <div style={{ background: '#fef2f2', border: '2px solid #dc2626', padding: 8, borderRadius: 6, marginTop: 8 }}><b>🚨 Красные флаги — срочно к врачу (не диагноз, а повод):</b><ul>{flags.map((f: any) => <li key={f.id}><b>{f.sign}.</b> {f.action}</li>)}</ul></div>}
    {!loading && r.length === 0 && !err && <p style={{ color: '#6b7280' }}>Введите симптомы и нажмите «Ранжировать».</p>}
    {why && <p style={{ background: '#eff6ff', padding: 8, borderRadius: 6 }}>🩺 <b>Почему на первом месте:</b> {why}{expl && <span><br />{expl}</span>}</p>}
    {r.map((x: any, i: number) => <div key={i} style={{ border: i === 0 ? '2px solid #16a34a' : '1px solid #ddd', margin: 6, padding: 6 }}><b>{i + 1}. {x.nosology}</b> [{(x.icd10 || []).join(',')}] score={x.score} — совпало: {x.matched.join('; ')}{x.key_signs && x.key_signs.length > 0 && <span><br /><i>Ключевые признаки: {x.key_signs.join('; ')}</i></span>}</div>)}</div>;
}
export function Referral() {
  const [docs, setDocs] = React.useState<any[]>([]);
  const [id, setId] = React.useState(''); const [crit, setCrit] = React.useState('мастоидит, парез лицевого нерва'); const [r, setR] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  React.useEffect(() => { api('/protocols?q=').then(d => setDocs(d.items || [])).catch(() => {}); }, []);
  const go = async () => {
    if (!id) { setErr('Выберите протокол из списка.'); return; }
    setErr('');
    try {
      const ans: any = {}; crit.split(',').map(x => x.trim()).filter(Boolean).forEach(k => ans[k] = true);
      setR(await api('/referral-check', { method: 'POST', body: JSON.stringify({ doc_id: id, answers: ans }) }));
    } catch (e) { setErr('Ошибка: ' + (e instanceof Error ? e.message : String(e))); }
  };
  return <div><h2>Критерии направления / госпитализации</h2>
    Протокол: <select value={id} onChange={e => setId(e.target.value)} style={{ maxWidth: '100%' }}>
      <option value="">— выберите протокол —</option>
      {docs.map((d: any) => <option key={d.document_id} value={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(', ')}]</option>)}
    </select><br />
    Критерии (через запятую): <input value={crit} onChange={e => setCrit(e.target.value)} style={{ width: '60%' }} /> <button onClick={go}>Проверить</button>
    {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
    {!docs.length && <p style={{ color: '#6b7280' }}>Список протоколов недоступен (нужен запуск backend).</p>}
    {r && <p><b>{r.verdict}</b></p>}</div>;
}
export function History() {
  const [h, setH] = React.useState<any[]>([]);
  React.useEffect(() => { api('/history').then(d => setH(d.items || [])); }, []);
  return <div><h2>История запросов</h2>{h.length === 0 && <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}><ArtEmpty /><p style={{ color: '#6b7280' }}>Пока пусто — задайте первый вопрос в разделе «Чат».</p></div>}{h.map((x: any, i: number) => <div key={i} style={{ borderBottom: '1px solid #eee', padding: 4 }}>{x.query} <i>[{x.intent}]{x.refused ? ' — отказ' : ''}</i></div>)}</div>;
}
export function Templates() {
  const [docs, setDocs] = React.useState<any[]>([]);
  const [id, setId] = React.useState(''); const [t, setT] = React.useState('');
  const [err, setErr] = React.useState('');
  React.useEffect(() => { api('/protocols?q=').then(d => setDocs(d.items || [])).catch(() => {}); }, []);
  const go = async (k: string) => {
    if (!id) { setErr('Сначала выберите протокол из списка.'); return; }
    setErr('');
    try { setT((await api(`/templates/${k}/${id}`)).text); } catch (e) { setErr('Ошибка: ' + (e instanceof Error ? e.message : String(e))); }
  };
  return <div><h2>Шаблоны заключений</h2>
    Протокол: <select value={id} onChange={e => setId(e.target.value)} style={{ maxWidth: '100%' }}>
      <option value="">— выберите протокол —</option>
      {docs.map((d: any) => <option key={d.document_id} value={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(', ')}]</option>)}
    </select>{' '}
    <button onClick={() => go('zaklyuchenie')}>Заключение</button> <button onClick={() => go('napravlenie')}>Направление</button>
    {err && <p style={{ color: '#b91c1c' }}>{err}</p>}
    <pre style={{ whiteSpace: 'pre-wrap' }}>{t}</pre></div>;
}
export function Admin() {
  const [email, setEmail] = React.useState('admin@lorai.local'); const [pw, setPw] = React.useState('admin123'); const [docs, setDocs] = React.useState<any[]>([]);
  const [stats, setStats] = React.useState<any>(null); const [contra, setContra] = React.useState<any[]>([]);
  const loginGo = async () => { const { login } = await import('../api/client'); const r = await login(email, pw); localStorage.setItem('token', r.token); setDocs((await api('/admin/documents')).items || []); };
  const loadStats = async () => { setStats(await api('/admin/stats')); };
  const loadContra = async () => { setContra((await api('/contradictions')).items || []); };
  const upload = async (f: File) => { const fd = new FormData(); fd.append('f', f); const t = localStorage.getItem('token'); const r = await fetch('http://localhost:8000/admin/upload', { method: 'POST', headers: { Authorization: 'Bearer ' + t }, body: fd }); alert(await r.text()); };
  return <div><h2>Админ-панель</h2><input value={email} onChange={e => setEmail(e.target.value)} /><input type="password" value={pw} onChange={e => setPw(e.target.value)} /><button onClick={loginGo}>Войти и показать документы</button><br />Загрузить PDF: <input type="file" accept=".pdf,.txt" onChange={e => e.target.files && upload(e.target.files[0])} />{docs.map((d: any) => <div key={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(',')}] conf={d.confidence}</div>)}
    <h3>Аналитика использования</h3><button onClick={loadStats}>Обновить статистику</button>
    {stats ? <div style={{ fontSize: 14 }}>
      <p>Документов: {stats.documents} · Запросов: {stats.queries_total} · Отказов: {stats.queries_refused} ({(stats.refusal_rate * 100).toFixed(1)}%)</p>
      <p>Оценки ответов: 👍 {stats.feedback?.up} / 👎 {stats.feedback?.down} · Среднее время ответа: {stats.avg_latency_ms ?? '—'} мс · Кэш: {stats.cache?.hits} попаданий / {stats.cache?.misses} промахов</p>
      {stats.knowledge_gaps?.length > 0 ? <span><b>Пробелы базы знаний (частые «нет данных» — сигнал догрузить КР):</b><ul>{stats.knowledge_gaps.map((g: any, i: number) => <li key={i}>{g.query} — {g.count} раз(а)</li>)}</ul></span> : <p style={{ color: '#6b7280' }}>Пробелов в базе не зафиксировано.</p>}
    </div> : <p style={{ color: '#6b7280' }}>Нажмите «Обновить статистику».</p>}
    <h3>Противоречия в базе</h3><button onClick={loadContra}>Проверить противоречия</button>
    {contra.length === 0 ? <p style={{ color: '#6b7280' }}>Не проверялось или противоречий нет.</p> : contra.map((x: any, i: number) => <div key={i} style={{ border: '1px solid #f59e0b', margin: 6, padding: 6 }}><b>{x.doc_a?.title}</b> ↔ <b>{x.doc_b?.title}</b> (общие МКБ: {(x.shared_icd || []).join(', ')})<br />Только в первом: {(x.only_in_a || []).join(', ') || '—'}; только во втором: {(x.only_in_b || []).join(', ') || '—'}<br /><i>{x.note}</i></div>)}
  </div>;
}
