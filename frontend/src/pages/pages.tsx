import React, { useState } from 'react';
import { api } from '../api/client';
export function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  React.useEffect(() => { api('/admin/documents').then(d => setStats({ docs: d.items?.length })).catch(() => api('/protocols?q=').then(d => setStats({ docs: d.items?.length }))); }, []);
  return <div><h2>Дашборд</h2><p>Документов в базе: {stats?.docs ?? '…'}</p></div>;
}
export function Chat() {
  const [q, setQ] = React.useState('Острый средний отит: диагностика и лечение?');
  const [a, setA] = React.useState('');
  const [sources, setSources] = React.useState<any[]>([]);
  const ask = async () => { const r = await api('/chat', { method: 'POST', body: JSON.stringify({ query: q }) }); setA(r.answer || r.warning); setSources(r.sources || []); };
  return <div><h2>Чат-ассистент (RAG)</h2><p style={{ background: '#fef3c7', padding: 8, borderRadius: 6 }}>⚠️ Не вводите персональные данные пациента (ФИО, паспорт, телефон, СНИЛС).</p><textarea value={q} onChange={e => setQ(e.target.value)} rows={3} style={{ width: '100%' }} /><br /><button onClick={ask}>Спросить</button><pre style={{ whiteSpace: 'pre-wrap', background: '#f3f4f6', padding: 12 }}>{a}</pre>{sources.length > 0 && <div><h4>Источники</h4>{sources.map((s: any, i: number) => <div key={i} style={{ border: '1px solid #ddd', margin: 4, padding: 6 }}>[Документ: {s.document || s.title || s.nosology}, Раздел: {s.section}, Стр.: {Array.isArray(s.page_range) ? s.page_range.join(', ') : s.page_range}] (score={s.score})</div>)}</div>}</div>;
}
export function ProtocolSearch() {
  const [q, setQ] = React.useState('H66'); const [items, setItems] = React.useState<any[]>([]);
  const go = async () => { const r = await api('/protocols?q=' + encodeURIComponent(q)); setItems(r.items || []); };
  React.useEffect(() => { go(); }, []);
  return <div><h2>Поиск протокола</h2><input value={q} onChange={e => setQ(e.target.value)} /><button onClick={go}>Найти</button>{items.map((p: any) => <div key={p.document_id} style={{ border: '1px solid #ddd', margin: 6, padding: 6 }}><b>{p.nosology}</b> [{(p.icd10_codes || []).join(', ')}] <a href={'#/checklist/' + p.document_id}>чек-лист</a></div>)}</div>;
}
export function DosageCalc() {
  const [w, setW] = React.useState('20'); const [m, setM] = React.useState('40'); const [r, setR] = React.useState<any>(null);
  const go = async () => setR(await api('/dosage', { method: 'POST', body: JSON.stringify({ weight_kg: +w, mg_per_kg: +m }) }));
  return <div><h2>Калькулятор дозировок</h2>Вес (кг): <input value={w} onChange={e => setW(e.target.value)} /> мг/кг: <input value={m} onChange={e => setM(e.target.value)} /> <button onClick={go}>Рассчитать</button>{r && <p>Разовая доза: <b>{r.single_dose_mg} мг</b>. {r.warning}</p>}</div>;
}
export function ChecklistPage() {
  const id = window.location.hash.split('/')[2] || '';
  const [c, setC] = React.useState<any>(null);
  React.useEffect(() => { if (id) api('/checklist/' + id).then(setC); }, [id]);
  if (!id) return <div>Откройте чек-лист из поиска протокола.</div>;
  return <div><h2>Чек-лист приёма: {c?.nosology}</h2>{(c?.checklist || []).map((b: any, i: number) => <div key={i}><h4>{b.block}</h4><ul>{b.points.map((p: string, j: number) => <li key={j}><label><input type="checkbox" /> {p}</label></li>)}</ul></div>)}<button onClick={() => window.print()}>Печать / PDF</button></div>;
}
export function DiffDx() {
  const [s, setS] = React.useState('оталгия, лихорадка'); const [r, setR] = React.useState<any[]>([]);
  const go = async () => setR((await api('/diff-diagnosis', { method: 'POST', body: JSON.stringify({ symptoms: s.split(/[,\n]/).map(x => x.trim()).filter(Boolean) }) })).ranked || []);
  return <div><h2>Дифференциальная диагностика</h2>Симптомы (через запятую): <input value={s} onChange={e => setS(e.target.value)} style={{ width: '60%' }} /> <button onClick={go}>Ранжировать</button>{r.map((x: any, i: number) => <div key={i} style={{ border: '1px solid #ddd', margin: 6, padding: 6 }}><b>{x.nosology}</b> [{(x.icd10 || []).join(',')}] score={x.score} — совпало: {x.matched.join('; ')}</div>)}</div>;
}
export function Referral() {
  const [id, setId] = React.useState(''); const [crit, setCrit] = React.useState('мастоидит, парез лицевого нерва'); const [r, setR] = React.useState<any>(null);
  const go = async () => { const ans: any = {}; crit.split(',').map(x => x.trim()).filter(Boolean).forEach(k => ans[k] = true); setR(await api('/referral-check', { method: 'POST', body: JSON.stringify({ doc_id: id, answers: ans }) })); };
  return <div><h2>Критерии направления / госпитализации</h2>ID протокола: <input value={id} onChange={e => setId(e.target.value)} style={{ width: '50%' }} /><br />Критерии (запятая): <input value={crit} onChange={e => setCrit(e.target.value)} style={{ width: '60%' }} /> <button onClick={go}>Проверить</button>{r && <p><b>{r.verdict}</b></p>}</div>;
}
export function History() {
  const [h, setH] = React.useState<any[]>([]);
  React.useEffect(() => { api('/history').then(d => setH(d.items || [])); }, []);
  return <div><h2>История запросов</h2>{h.map((x: any, i: number) => <div key={i} style={{ borderBottom: '1px solid #eee', padding: 4 }}>{x.query} <i>[{x.intent}]{x.refused ? ' — отказ' : ''}</i></div>)}</div>;
}
export function Templates() {
  const [id, setId] = React.useState(''); const [t, setT] = React.useState('');
  const go = async (k: string) => setT((await api(`/templates/${k}/${id}`)).text);
  return <div><h2>Шаблоны заключений</h2>ID протокола: <input value={id} onChange={e => setId(e.target.value)} /> <button onClick={() => go('zaklyuchenie')}>Заключение</button> <button onClick={() => go('napravlenie')}>Направление</button><pre style={{ whiteSpace: 'pre-wrap' }}>{t}</pre></div>;
}
export function Admin() {
  const [email, setEmail] = React.useState('admin@lorai.local'); const [pw, setPw] = React.useState('admin123'); const [docs, setDocs] = React.useState<any[]>([]);
  const loginGo = async () => { const { login } = await import('../api/client'); const r = await login(email, pw); localStorage.setItem('token', r.token); setDocs((await api('/admin/documents')).items || []); };
  const upload = async (f: File) => { const fd = new FormData(); fd.append('f', f); const t = localStorage.getItem('token'); const r = await fetch('http://localhost:8000/admin/upload', { method: 'POST', headers: { Authorization: 'Bearer ' + t }, body: fd }); alert(await r.text()); };
  return <div><h2>Админ-панель</h2><input value={email} onChange={e => setEmail(e.target.value)} /><input type="password" value={pw} onChange={e => setPw(e.target.value)} /><button onClick={loginGo}>Войти и показать документы</button><br />Загрузить PDF: <input type="file" accept=".pdf,.txt" onChange={e => e.target.files && upload(e.target.files[0])} />{docs.map((d: any) => <div key={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(',')}] conf={d.confidence}</div>)}</div>;
}
