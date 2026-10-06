import React, { useState } from 'react';
import { API, api } from '../api/client';
import { ArtChat, ArtEmpty, ArtOnboarding, ArtSearch } from '../components/illustrations';

function confPill(score: number | undefined): [string, string] {
  if ((score ?? 0) >= 0.5) return ['высокая', 'pill pill-ok'];
  if ((score ?? 0) >= 0.2) return ['средняя', 'pill pill-warn'];
  return ['низкая', 'pill pill-mute'];
}
function confAnyPill(c: unknown): string {
  if (typeof c === 'number') return confPill(c)[1];
  const s = String(c ?? '').toLowerCase();
  if (s.startsWith('high') || s === 'ok') return 'pill pill-ok';
  if (s.startsWith('med')) return 'pill pill-warn';
  if (s) return 'pill pill-mute';
  return 'pill pill-mute';
}
const confLabel = (c: unknown): string =>
  typeof c === 'number' ? c.toFixed(2) : String(c ?? '—');

export function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [onb, setOnb] = useState(() => localStorage.getItem('lorai_onb') !== 'done');
  React.useEffect(() => { api('/health').then(h => setStats({ docs: h.documents })).catch(() => api('/protocols?q=отит').then(d => setStats({ docs: d.items?.length })).catch(() => {})); }, []);
  const done = () => { localStorage.setItem('lorai_onb', 'done'); setOnb(false); };
  return (
    <div className="stagger">
      {onb && (
        <div className="panel panel-info onboard" role="status">
          <ArtOnboarding />
          <div>
            <b>Добро пожаловать в ЛОРАИ</b> — помощник по клиническим рекомендациям (ЛОР).
            <ol>
              <li><b>Чат</b> — клинический вопрос, ответ с цитатами протоколов.</li>
              <li><b>Протоколы</b> — точная выдача по нозологии/МКБ без ИИ.</li>
              <li><b>Дифдиагностика</b> — ранжирование нозологий по симптомам.</li>
            </ol>
            <button className="btn btn-secondary btn-sm" style={{ marginTop: 8 }} onClick={done}>Понятно, скрыть</button>
          </div>
        </div>
      )}
      <div className="stats-grid">
        <div className="stat">
          <span className="stat-v num">{stats?.docs ?? '…'}</span>
          <span className="stat-l">клинических рекомендаций в базе</span>
        </div>
        <div className="stat">
          <span className="stat-v num">6</span>
          <span className="stat-l">рабочих инструментов: чат, протоколы, дифдиагностика, дозировки, калькуляторы, шаблоны</span>
        </div>
      </div>
      <div className="card">
        <h2>Быстрый старт</h2>
        <div className="quick-links">
          <a href="#/chat">Чат-ассистент</a>
          <a href="#/protocols">Клинические рекомендации</a>
          <a href="#/diff">Дифдиагностика</a>
          <a href="#/dosage">Дозировки</a>
          <a href="#/calc">Калькуляторы</a>
          <a href="#/checklist">Чек-лист приёма</a>
        </div>
      </div>
    </div>
  );
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
            } else if (e.type === 'corrected' && e.text) {
              acc = e.text; // проверка цифр скорректировала ответ — заменяем целиком
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
  const [repOpen, setRepOpen] = React.useState(false);
  const [repText, setRepText] = React.useState('');
  const [repDone, setRepDone] = React.useState(false);
  const sendReport = async () => {
    if (!repText.trim()) return;
    try {
      const ctx = `[сессия ${(sid || '').slice(0, 8)}] [score ${meta?.top_score ?? '?'}] ` +
        `Вопрос: ${q.slice(0, 300)} | Ответ: ${a.slice(0, 500)} || Проблема: ${repText.trim()}`;
      await api('/feedback', { method: 'POST', body: JSON.stringify({ query: q, vote: -1, comment: ctx.slice(0, 2000) }) });
      setRepDone(true); setRepOpen(false); setRepText('');
    } catch { setErr('Сообщить не удалось (нужен вход). Войдите — токен сохраняется.'); }
  };
  const [confLabelTxt, confCls] = confPill(meta?.top_score);
  return (
    <div className="stagger">
      <div>
        <h2>Чат-ассистент (RAG)</h2>
        <p className="pii-note">⚠️ Не вводите персональные данные пациента (ФИО, паспорт, телефон, СНИЛС).</p>
        <textarea value={q} onChange={e => setQ(e.target.value)} rows={3} aria-label="Клинический вопрос" />
        <div className="ask-row">
          <button className="btn" onClick={ask} disabled={loading}>
            {loading ? (streaming ? 'Получаю ответ…' : 'Думаю…') : 'Спросить'}
          </button>
          {streaming && <button className="btn btn-secondary" onClick={() => { (stopRef as any).stop = true; }}>Остановить</button>}
          {sid && <span className="muted" style={{ alignSelf: 'center' }}>сессия {sid.slice(0, 8)}… (помнит контекст)</span>}
        </div>
      </div>
      {loading && !a && (
        <div role="status" aria-label="Генерирую ответ" style={{ display: 'grid', gap: 8 }}>
          <div className="skeleton" style={{ height: 18 }} />
          <div className="skeleton" style={{ height: 18, width: '78%' }} />
          <div className="skeleton" style={{ height: 18, width: '46%' }} />
        </div>
      )}
      {err && <div className="error-box" role="alert">{err}</div>}
      {!loading && !a && !meta?.needs_clarification && !err && (
        <div className="empty"><ArtChat /><p>Здесь появится ответ с цитатами клинических рекомендаций.</p></div>
      )}
      {meta?.needs_clarification && (
        <div className="clarify" role="status"><b>Уточните, пожалуйста:</b> {meta.clarifying_question}</div>
      )}
      {a && (
        <div>
          <div className="row" style={{ gap: 8, marginTop: 4 }}>
            <span className={confCls}>уверенность: {confLabelTxt} (score={meta?.top_score?.toFixed?.(2) ?? meta?.top_score})</span>
            {meta?.cached && <span className="pill pill-mute">из кэша · {meta?.latency_ms} мс</span>}
            {meta?.doc_count > 1 && <span className="pill pill-mute">синтез из {meta.doc_count} документов</span>}
          </div>
          <div className="answer">{a}{streaming && <span className="stream-caret" aria-hidden="true" />}</div>
          <div className="vote-row">
            <span className="muted">Ответ полезен?</span>
            <button onClick={() => vote(1)} disabled={voted !== 0} aria-label="Ответ полезен">{voted === 1 ? '👍 спасибо!' : '👍'}</button>
            <button onClick={() => vote(-1)} disabled={voted !== 0} aria-label="Ответ не полезен">{voted === -1 ? '👎 принято' : '👎'}</button>
            <button className="btn btn-ghost btn-sm" onClick={() => { setRepOpen(!repOpen); setRepDone(false); }}>Сообщить о проблеме</button>
          </div>
          {repDone && <p className="panel panel-ok" style={{ marginTop: 8 }}>Спасибо. Сообщение с контекстом экрана отправлено разработчикам.</p>}
          {repOpen && (
            <div className="panel" style={{ marginTop: 8 }}>
              <label className="field">Что не так с этим ответом?
                <textarea value={repText} onChange={(e) => setRepText(e.target.value)} rows={2}
                  placeholder="Например: неверная дозировка, не тот протокол…" />
              </label>
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn btn-sm" onClick={sendReport} disabled={!repText.trim()}>
                  Отправить (с вопросом, ответом и оценкой — без персональных данных)
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      {sources.length > 0 && (
        <details>
          <summary>Источники ({sources.length})</summary>
          <div className="src-list">
            {sources.map((s: any, i: number) => (
              <div key={i} className="source-card">
                <div>
                  <span className="src-doc">{s.document || s.title || s.nosology}</span>
                  <span className="src-meta">Раздел: {s.section} · стр. {Array.isArray(s.page_range) ? s.page_range.join(', ') : s.page_range}</span>
                </div>
                <span className="pill pill-mute num">{typeof s.score === 'number' ? s.score.toFixed(2) : s.score}</span>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
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
  return (
    <div className="stagger">
      <div>
        <h2>Поиск протокола</h2>
        <div className="form-line">
          <input value={q} onChange={e => setQ(e.target.value)} aria-label="Нозология или код МКБ" placeholder="Код МКБ или название, например H66" />
          <button className="btn" onClick={go} disabled={loading}>{loading ? 'Ищу…' : 'Найти'}</button>
        </div>
      </div>
      {err && <div className="error-box" role="alert">{err}</div>}
      {!loading && items.length === 0 && !err && (
        <div className="empty"><ArtSearch /><p>Ничего не найдено. Попробуйте код МКБ (например, H66) или другое название. Точный поиск работает и без чата.</p></div>
      )}
      {items.map((p: any) => (
        <div key={p.document_id}>
          <div className="doc-row">
            <b>{p.nosology}</b>
            {(p.icd10_codes || []).map((c: string) => <span key={c} className="icd">{c}</span>)}
            <a className="btn btn-sm btn-secondary" href={'#/checklist/' + p.document_id}>Чек-лист</a>
            <button className="btn btn-sm btn-ghost" onClick={() => showRelated(p.document_id)}>
              {rel[p.document_id] ? 'Скрыть похожие' : 'Похожие'}
            </button>
            <button className="btn btn-sm btn-ghost" onClick={() => addFav(p.document_id)} title="В избранное" aria-label="Добавить в избранное">⭐</button>
            {rel[p.document_id] && (
              <div className="doc-extra">
                {rel[p.document_id].length === 0
                  ? <p className="muted" style={{ margin: 0 }}>Похожих протоколов не найдено.</p>
                  : <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                    {rel[p.document_id].map((r: any) => (
                      <li key={r.document_id} style={{ margin: '3px 0' }}>
                        {r.nosology} [{(r.icd10_codes || []).join(', ')}] — {(r.reasons || []).join('; ')}
                      </li>
                    ))}
                  </ul>}
              </div>
            )}
          </div>
        </div>
      ))}
      <h3>⭐ Моё избранное</h3>
      {favHint && favs.length === 0 && <p className="muted">Войдите в разделе «Админ», чтобы сохранять избранные протоколы.</p>}
      {favs.map((f: any) => (
        <div key={f.id} className="doc-row">
          <b>{f.doc_id}</b>
          {f.note && <i className="muted">({f.note})</i>}
          <button className="btn btn-sm btn-ghost" onClick={() => delFav(f.id)} aria-label="Удалить из избранного">✕</button>
        </div>
      ))}
    </div>
  );
}

export function DosageCalc() {
  const [w, setW] = React.useState('20'); const [m, setM] = React.useState('40'); const [r, setR] = React.useState<any>(null);
  const go = async () => setR(await api('/dosage', { method: 'POST', body: JSON.stringify({ weight_kg: +w, mg_per_kg: +m }) }));
  return (
    <div className="stagger">
      <div>
        <h2>Калькулятор дозировок</h2>
        <div className="form-line">
          <input value={w} onChange={e => setW(e.target.value)} inputMode="decimal" aria-label="Вес, кг" placeholder="Вес, кг" />
          <input value={m} onChange={e => setM(e.target.value)} inputMode="decimal" aria-label="Доза, мг/кг" placeholder="мг/кг" />
          <button className="btn" onClick={go}>Рассчитать</button>
        </div>
      </div>
      {r && (
        <div className="panel panel-ok">
          Разовая доза: <b className="num" style={{ fontSize: 19 }}>{r.single_dose_mg} мг</b>
          <p className="muted" style={{ margin: '4px 0 0' }}>{r.warning}</p>
        </div>
      )}
    </div>
  );
}

export function Calculators() {
  const [fever, setFever] = React.useState(false); const [exudate, setExudate] = React.useState(false);
  const [nodes, setNodes] = React.useState(false); const [noCough, setNoCough] = React.useState(false);
  const [age, setAge] = React.useState('15-44'); const [centor, setCentor] = React.useState<any>(null);
  const [pta, setPta] = React.useState(['20', '20', '25', '15']); const [ptaR, setPtaR] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  const goCentor = async () => { setErr(''); try { setCentor(await api('/calculators/centor', { method: 'POST', body: JSON.stringify({ fever, exudate, nodes, no_cough: noCough, age_band: age }) })); } catch (e) { setErr('Ошибка Centor: ' + (e instanceof Error ? e.message : String(e))); } };
  const goPta = async () => { setErr(''); try { setPtaR(await api('/calculators/pta', { method: 'POST', body: JSON.stringify({ thresholds_db: pta.map(Number) }) })); } catch (e) { setErr('Ошибка PTA: ' + (e instanceof Error ? e.message : String(e))); } };
  return (
    <div className="stagger">
      <div>
        <h2>Клинические калькуляторы</h2>
        <p className="muted">Чистые формулы по опубликованным шкалам, без ИИ. Решение всегда за врачом.</p>
      </div>
      {err && <div className="error-box" role="alert">{err}</div>}
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Шкала Centor/McIsaac (фарингит)</h3>
        <div style={{ display: 'grid', gap: 6, maxWidth: 460 }}>
          <label className="check"><input type="checkbox" checked={fever} onChange={e => setFever(e.target.checked)} /> Температура ≥38°C</label>
          <label className="check"><input type="checkbox" checked={exudate} onChange={e => setExudate(e.target.checked)} /> Налёт/экссудат на миндалинах</label>
          <label className="check"><input type="checkbox" checked={nodes} onChange={e => setNodes(e.target.checked)} /> Болезненные шейные лимфоузлы</label>
          <label className="check"><input type="checkbox" checked={noCough} onChange={e => setNoCough(e.target.checked)} /> Кашля нет</label>
        </div>
        <div className="form-line" style={{ marginTop: 10 }}>
          <select value={age} onChange={e => setAge(e.target.value)} aria-label="Возраст">
            <option value="3-14">3–14 лет</option>
            <option value="15-44">15–44</option>
            <option value="45+">45+</option>
          </select>
          <button className="btn" onClick={goCentor}>Посчитать</button>
        </div>
        {centor && (
          <div className="panel panel-ok" style={{ marginTop: 10 }}>
            Баллов: <b className="num">{centor.score} из {centor.max}</b> — {centor.interpretation}
            <p className="muted" style={{ margin: '4px 0 0' }}>{centor.recommendation}</p>
          </div>
        )}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Средний порог слуха PTA (0.5/1/2/4 кГц, дБ)</h3>
        <div className="form-line">
          {pta.map((v, i) => (
            <input key={i} className="freq-input num" value={v}
              onChange={e => { const c = [...pta]; c[i] = e.target.value; setPta(c); }}
              inputMode="numeric" aria-label={'Порог ' + (i + 1) + ' частоты, дБ'} />
          ))}
          <button className="btn" onClick={goPta}>Посчитать</button>
        </div>
        {ptaR && (
          <div className="panel panel-ok" style={{ marginTop: 10 }}>
            Среднее: <b className="num" style={{ fontSize: 19 }}>{ptaR.average_db} дБ</b> — {ptaR.grade}
            <p className="muted" style={{ margin: '4px 0 0' }}>{ptaR.recommendation}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export function ChecklistPage() {
  const id = window.location.hash.split('/')[2] || '';
  const [c, setC] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  React.useEffect(() => { if (id) api('/checklist/' + id).then(setC).catch(() => setErr('Чек-лист недоступен: нет соединения с сервером.')); }, [id]);
  if (!id) return (
    <div>
      <h2>Чек-лист приёма</h2>
      <div className="empty"><ArtEmpty /><p>Откройте чек-лист из поиска протокола — там кнопка «Чек-лист» у каждой нозологии.</p></div>
    </div>
  );
  return (
    <div className="checklist-print">
      <style>{'@media print { button { display: none; } body { font-size: 12pt; } }'}</style>
      <h2>Чек-лист приёма: {c?.nosology ?? '…'}</h2>
      {err && <div className="error-box" role="alert">{err}</div>}
      {!c && !err && (
        <div role="status" aria-label="Загружаю чек-лист" style={{ display: 'grid', gap: 8 }}>
          <div className="skeleton" style={{ height: 18, width: '60%' }} />
          <div className="skeleton" style={{ height: 18 }} />
          <div className="skeleton" style={{ height: 18, width: '80%' }} />
        </div>
      )}
      {(c?.checklist || []).map((b: any, i: number) => (
        <div key={i}>
          <h4>{b.block}</h4>
          <ul>
            {b.points.map((p: string, j: number) => (
              <li key={j}><label><input type="checkbox" /> {p}</label></li>
            ))}
          </ul>
        </div>
      ))}
      <button className="btn no-print" onClick={() => window.print()}>Печать / PDF</button>
    </div>
  );
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
  return (
    <div className="stagger">
      <div>
        <h2>Дифференциальная диагностика</h2>
        <div className="form-line">
          <input value={s} onChange={e => setS(e.target.value)} aria-label="Симптомы" placeholder="Симптомы через запятую" />
          <button className="btn" onClick={go} disabled={loading}>{loading ? 'Анализирую…' : 'Ранжировать'}</button>
        </div>
      </div>
      {err && <div className="error-box" role="alert">{err}</div>}
      {flags.length > 0 && (
        <div className="panel panel-danger" role="alert">
          <b>🚨 Красные флаги — срочно к врачу (не диагноз, а повод):</b>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {flags.map((f: any) => <li key={f.id} style={{ margin: '3px 0' }}><b>{f.sign}.</b> {f.action}</li>)}
          </ul>
        </div>
      )}
      {!loading && r.length === 0 && !err && <p className="muted">Введите симптомы и нажмите «Ранжировать».</p>}
      {why && (
        <div className="panel panel-info">
          <b>🩺 Почему на первом месте:</b> {why}
          {expl && <p className="muted" style={{ margin: '6px 0 0' }}>{expl}</p>}
        </div>
      )}
      {r.map((x: any, i: number) => (
        <div key={i} className={'rank-card' + (i === 0 ? ' top' : '')}>
          <span className="rank-num">{i + 1}</span>
          <span className="rank-name">{x.nosology} {(x.icd10 || []).map((c: string) => <span key={c} className="icd" style={{ marginLeft: 6 }}>{c}</span>)}</span>
          <span className="score-bar" title={'score ' + x.score}><i style={{ width: Math.min(100, Math.round((x.score ?? 0) * 100)) + '%' }} /></span>
          <span className="rank-sub">совпало: {x.matched.join('; ')}{x.matched.length === 0 ? '—' : ''}</span>
          <span className="match-chips">
            {(x.key_signs || []).map((k: string) => <span key={k}>{k}</span>)}
          </span>
        </div>
      ))}
    </div>
  );
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
  return (
    <div className="stagger">
      <div>
        <h2>Критерии направления / госпитализации</h2>
        <div className="form-line">
          <select value={id} onChange={e => setId(e.target.value)} aria-label="Протокол">
            <option value="">— выберите протокол —</option>
            {docs.map((d: any) => <option key={d.document_id} value={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(', ')}]</option>)}
          </select>
          <input value={crit} onChange={e => setCrit(e.target.value)} aria-label="Критерии" placeholder="Критерии через запятую" />
          <button className="btn" onClick={go}>Проверить</button>
        </div>
      </div>
      {err && <div className="error-box" role="alert">{err}</div>}
      {!docs.length && <p className="muted">Список протоколов недоступен (нужен запуск backend).</p>}
      {r && <div className="panel panel-ok"><b>{r.verdict}</b></div>}
    </div>
  );
}

export function History() {
  const [h, setH] = React.useState<any[]>([]);
  const [err, setErr] = React.useState('');
  React.useEffect(() => { api('/history').then(d => setH(d.items || [])).catch(() => setErr('История недоступна (нужен вход и запуск backend).')); }, []);
  return (
    <div className="stagger">
      <div>
        <h2>История запросов</h2>
        <p className="muted">Последние обращения в чат — по ним видно, что врачи спрашивают чаще всего.</p>
      </div>
      {err && <div className="error-box" role="alert">{err}</div>}
      {!err && h.length === 0 && (
        <div className="empty"><ArtEmpty /><p>Пока пусто — задайте первый вопрос в разделе «Чат».</p></div>
      )}
      {h.map((x: any, i: number) => (
        <div key={i} className="doc-row">
          <span style={{ flex: '1 1 240px' }}>{x.query}</span>
          <span className="pill pill-mute">{x.intent}</span>
          {x.refused && <span className="pill pill-danger">отказ</span>}
        </div>
      ))}
    </div>
  );
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
  return (
    <div className="stagger">
      <div>
        <h2>Шаблоны заключений</h2>
        <div className="form-line">
          <select value={id} onChange={e => setId(e.target.value)} aria-label="Протокол">
            <option value="">— выберите протокол —</option>
            {docs.map((d: any) => <option key={d.document_id} value={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(', ')}]</option>)}
          </select>
          <button className="btn" onClick={() => go('zaklyuchenie')}>Заключение</button>
          <button className="btn btn-secondary" onClick={() => go('napravlenie')}>Направление</button>
        </div>
      </div>
      {err && <div className="error-box" role="alert">{err}</div>}
      {!t && !err && <p className="muted">Выберите протокол и тип документа — текст появится здесь, готовый к копированию.</p>}
      {t && <pre>{t}</pre>}
    </div>
  );
}

export function Admin() {
  const [email, setEmail] = React.useState('admin@lorai.local'); const [pw, setPw] = React.useState('admin123'); const [docs, setDocs] = React.useState<any[]>([]);
  const [stats, setStats] = React.useState<any>(null); const [contra, setContra] = React.useState<any[]>([]);
  const [uploading, setUploading] = React.useState(false);
  const [upResult, setUpResult] = React.useState<any>(null);
  const [upError, setUpError] = React.useState('');
  const loginGo = async () => { const { login } = await import('../api/client'); const r = await login(email, pw); localStorage.setItem('token', r.token); setDocs((await api('/admin/documents')).items || []); };
  const loadStats = async () => { setStats(await api('/admin/stats')); };
  const loadContra = async () => { setContra((await api('/contradictions')).items || []); };
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
      setDocs((await api('/admin/documents')).items || []);
    } catch (e) {
      setUpError(e instanceof Error && e.message ? e.message.slice(0, 300) : 'Загрузка не удалась. Проверьте соединение и попробуйте снова.');
    }
    setUploading(false);
  };
  return (
    <div className="stagger">
      <div>
        <h2>Админ-панель</h2>
        <div className="form-line">
          <input value={email} onChange={e => setEmail(e.target.value)} type="text" aria-label="E-mail" />
          <input type="password" value={pw} onChange={e => setPw(e.target.value)} aria-label="Пароль" />
          <button className="btn" onClick={loginGo}>Войти и показать документы</button>
        </div>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Загрузка клинической рекомендации</h3>
        <label className="btn btn-secondary file-btn">
          Загрузить PDF
          <input type="file" accept=".pdf,.txt" disabled={uploading} onChange={e => e.target.files && upload(e.target.files[0])} />
        </label>
        <span className="muted" style={{ marginLeft: 12 }}>PDF/TXT до 50 МБ · извлечение текста, разделов и кодов МКБ</span>
        {uploading && (
          <div role="status" aria-label="Обрабатывается файл" style={{ display: 'grid', gap: 8, marginTop: 12 }}>
            <div className="skeleton" style={{ height: 16, width: '70%' }} />
            <div className="skeleton" style={{ height: 16, width: '45%' }} />
            <span className="muted">Обрабатывается: извлечение текста, разделов и кодов МКБ…</span>
          </div>
        )}
        {upError && (
          <div className="error-box" role="alert" style={{ marginTop: 12 }}>
            <b>Не удалось обработать файл.</b> {upError}
            <div className="muted">Проверьте формат (PDF/TXT до 50 МБ) и попробуйте снова.</div>
          </div>
        )}
        {upResult && (
          <div className="panel panel-ok" style={{ marginTop: 12 }}>
            <b>Готово:</b> {upResult.nosology || upResult.title} [{(upResult.icd10 || []).join(', ')}] · статус {upResult.processing_status} · уверенность {upResult.confidence}
            {upResult.duplicate ? ' · обновлён существующий документ' : ''}
            {upResult.needs_review ? ' · требуется ручная проверка (низкая уверенность)' : ''}
            <p style={{ margin: '8px 0 0' }}><a href={'#/protocols'}>Проверить в поиске</a></p>
          </div>
        )}
        {docs.length > 0 && (
          <>
            <h3>Документы ({docs.length})</h3>
            {docs.map((d: any) => (
              <div key={d.document_id} className="doc-row">
                <b>{d.nosology}</b>
                {(d.icd10_codes || []).map((c: string) => <span key={c} className="icd">{c}</span>)}
                <span className={confAnyPill(d.confidence)}>conf {confLabel(d.confidence)}</span>
              </div>
            ))}
          </>
        )}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Аналитика использования</h3>
        <button className="btn btn-secondary btn-sm" onClick={loadStats}>Обновить статистику</button>
        {stats ? (
          <div className="stats-grid" style={{ marginTop: 12 }}>
            <div className="stat"><span className="stat-v num">{stats.documents}</span><span className="stat-l">документов в базе</span></div>
            <div className="stat"><span className="stat-v num">{stats.queries_total}</span><span className="stat-l">запросов всего</span></div>
            <div className="stat"><span className="stat-v num">{(stats.refusal_rate * 100).toFixed(1)}%</span><span className="stat-l">отказов: {stats.queries_refused}</span></div>
            <div className="stat"><span className="stat-v num">👍 {stats.feedback?.up} / 👎 {stats.feedback?.down}</span><span className="stat-l">оценки ответов</span></div>
            <div className="stat"><span className="stat-v num">{stats.avg_latency_ms ?? '—'}</span><span className="stat-l">мс — среднее время ответа</span></div>
            <div className="stat"><span className="stat-v num">{stats.cache?.hits}/{(stats.cache?.hits ?? 0) + (stats.cache?.misses ?? 0)}</span><span className="stat-l">кэш: попаданий / запросов</span></div>
          </div>
        ) : <p className="muted" style={{ marginTop: 10 }}>Нажмите «Обновить статистику».</p>}
        {stats?.knowledge_gaps?.length > 0 && (
          <div className="panel panel-warn" style={{ marginTop: 12 }}>
            <b>Пробелы базы знаний</b> (частые «нет данных» — сигнал догрузить КР):
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {stats.knowledge_gaps.map((g: any, i: number) => <li key={i}>{g.query} — {g.count} раз(а)</li>)}
            </ul>
          </div>
        )}
        {stats && !stats.knowledge_gaps?.length && <p className="muted">Пробелов в базе не зафиксировано.</p>}
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Противоречия в базе</h3>
        <button className="btn btn-secondary btn-sm" onClick={loadContra}>Проверить противоречия</button>
        {contra.length === 0 && <p className="muted" style={{ marginTop: 10 }}>Не проверялось или противоречий нет.</p>}
        {contra.map((x: any, i: number) => (
          <div key={i} className="panel panel-warn" style={{ marginTop: 10 }}>
            <b>{x.doc_a?.title}</b> ↔ <b>{x.doc_b?.title}</b> (общие МКБ: {(x.shared_icd || []).join(', ')})
            <p className="muted" style={{ margin: '6px 0 0' }}>
              Только в первом: {(x.only_in_a || []).join(', ') || '—'}; только во втором: {(x.only_in_b || []).join(', ') || '—'}
            </p>
            <i>{x.note}</i>
          </div>
        ))}
      </div>
    </div>
  );
}
