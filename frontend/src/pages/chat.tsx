import React from 'react';
import { api, apiStream, humanError } from '../api/client';
import { Button, Card, CopyButton, ErrorBox, PageHeader, Skeleton, toast } from '../components/common';
import { ArtChat } from '../components/illustrations';
import { Markdown } from '../components/markdown';
import { plainText } from '../lib/markdown';
import { readSession } from '../lib/auth';
import { confPill } from './shared';

interface Turn {
  id: number;
  q: string;
  a: string;
  sources: any[];
  meta: any;
  state: 'streaming' | 'done' | 'error' | 'stopped';
  error?: unknown;
  voted?: number;
}

const SUGGESTIONS = [
  'Острый средний отит у ребёнка 3 лет: лечение?',
  'Когда при остром тонзиллите нужен антибиотик?',
  'Красные флаги при боли в горле',
  'Средний отит: критерии направления к ЛОРу',
];

export function Chat() {
  const [input, setInput] = React.useState('Острый средний отит: диагностика и лечение?');
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [sid, setSid] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const abortRef = React.useRef<AbortController | null>(null);
  const stoppedRef = React.useRef(false);
  const idRef = React.useRef(0);
  const autoSentRef = React.useRef(false);
  const endRef = React.useRef<HTMLDivElement | null>(null);
  const session = readSession();

  const patch = (id: number, p: Partial<Turn>) =>
    setTurns((t) => t.map((x) => (x.id === id ? { ...x, ...p } : x)));

  /** Автопрокрутка к свежему тексту, пока врач сам не отлистал вверх. */
  const stickRef = React.useRef(true);
  React.useEffect(() => {
    const onScroll = () => {
      stickRef.current = window.innerHeight + window.scrollY >= document.body.scrollHeight - 260;
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  const scrollEnd = (smooth = false) =>
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ block: 'end', behavior: smooth ? 'smooth' : 'auto' }));

  const send = React.useCallback(async (raw: string) => {
    const q = raw.trim();
    if (!q || busy) return;
    const id = ++idRef.current;
    setTurns((t) => [...t, { id, q, a: '', sources: [], meta: null, state: 'streaming' }]);
    setInput('');
    setBusy(true);
    stoppedRef.current = false;
    stickRef.current = true;
    scrollEnd(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    let acc = '';
    let sawDone = false;
    let meta: any = null;

    /** Резервный путь: обычный POST /chat, если поток оборвался без ответа. */
    const loadFull = async () => {
      const r = await api('/chat', { method: 'POST', body: JSON.stringify({ query: q, session_id: sid || undefined }) });
      const text = r.answer || r.warning || '';
      if (r.session_id) setSid(r.session_id);
      patch(id, { a: text, sources: r.sources || [], meta: r, state: 'done' });
    };

    try {
      await apiStream('/chat/stream', { query: q, session_id: sid || undefined }, (e) => {
        if (e.type === 'meta') {
          meta = e;
          patch(id, { sources: (e as any).sources || [], meta: e });
          if ((e as any).session_id) setSid(String((e as any).session_id));
        } else if (e.type === 'token') {
          acc += (e as any).text || '';
          patch(id, { a: acc });
          if (stickRef.current) scrollEnd();
        } else if (e.type === 'corrected') {
          acc = (e as any).text || acc;
          patch(id, { a: acc });
        } else if (e.type === 'done') {
          sawDone = true;
          const warning = (e as any).warning;
          const finalText = warning ? warning : (acc || (e as any).answer || '');
          patch(id, { a: finalText, meta: { ...(meta || {}), ...e }, state: 'done' });
          if (stickRef.current) scrollEnd();
        }
      }, ctrl.signal);
      if (!sawDone) {
        if (stoppedRef.current) patch(id, { state: 'stopped' });
        else if (acc) patch(id, { state: 'done', meta: { ...(meta || {}), partial: true } });
        else {
          // Поток закончился без события done и без текста — добираем ответ обычным POST.
          console.warn('[chat] поток завершился без done — резервный POST /chat');
          await loadFull();
        }
      }
    } catch (err) {
      const aborted = stoppedRef.current || (err instanceof DOMException && err.name === 'AbortError');
      if (aborted) {
        patch(id, { state: 'stopped' });
      } else if (!acc) {
        console.warn('[chat] поток не удался, фолбэк на POST /chat', err);
        try {
          await loadFull();
        } catch (e2) {
          patch(id, { state: 'error', error: e2 });
        }
      } else {
        patch(id, { state: 'done', meta: { ...(meta || {}), partial: true } });
      }
    }
    if (abortRef.current === ctrl) abortRef.current = null;
    setBusy(false);
  }, [busy, sid]);

  /* «Быстрый вопрос» с дашборда: #/chat?q=… — вопрос сразу уходит в работу. */
  React.useEffect(() => {
    const read = () => new URLSearchParams(window.location.hash.split('?')[1] || '').get('q') || '';
    const q = read();
    if (q && !autoSentRef.current) {
      autoSentRef.current = true;
      setInput(q);
      send(q);
    }
    const onHash = () => {
      const v = read();
      if (v) setInput(v);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const stop = () => {
    stoppedRef.current = true;
    abortRef.current?.abort();
    toast('Генерация остановлена — текст выше сохранён', 'info');
  };

  const newDialog = () => {
    abortRef.current?.abort();
    setTurns([]);
    setSid('');
    setBusy(false);
  };

  const vote = async (t: Turn, v: number) => {
    if (!session) { toast('Оценивать ответы может только вошедший врач — войдите в разделе «Вход»', 'err'); return; }
    try {
      await api('/feedback', { method: 'POST', body: JSON.stringify({ query: t.q, vote: v }) });
      patch(t.id, { voted: v });
      toast(v === 1 ? 'Спасибо, оценка учтена' : 'Спасибо, разберём этот ответ', 'ok');
    } catch (e) {
      toast(humanError(e), 'err');
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send(input); }
    if (e.key === 'Escape' && busy) { e.preventDefault(); stop(); }
  };

  return (
    <div className="stagger">
      <PageHeader
        id="chat-title"
        title="Чат-ассистент (RAG)"
        sub="Ответ строится строго по загруженным клиническим рекомендациям; ниже — источники с разделами и страницами."
      />

      <Card labelledBy="chat-title">
        <p className="pii-note">⚠️ Не вводите персональные данные пациента (ФИО, паспорт, телефон, СНИЛС).</p>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={3}
          aria-label="Клинический вопрос"
          placeholder="Например: острый средний отит у ребёнка 3 лет — антибиотик первой линии и дозировка?"
        />
        <div className="ask-row">
          <Button onClick={() => send(input)} loading={busy} disabled={busy || !input.trim()}>
            {busy ? 'Отвечаю…' : turns.length ? 'Спросить ещё' : 'Спросить'}
          </Button>
          {busy && <Button variant="secondary" onClick={stop}>Остановить</Button>}
          {turns.length > 0 && !busy && <Button variant="ghost" onClick={newDialog}>Новый диалог</Button>}
          {sid && <span className="muted" style={{ alignSelf: 'center' }}>контекст диалога сохраняется (сессия {sid.slice(0, 8)}…)</span>}
        </div>
        <p className="caption" style={{ marginTop: 6 }}>Ctrl/⌘ + Enter — отправить, Esc — остановить генерацию.</p>
      </Card>

      {turns.length === 0 && (
        <Card>
          <div className="empty">
            <ArtChat />
            <div>
              <b>Здесь появится ответ с цитатами клинических рекомендаций</b>
              <div style={{ fontSize: 14 }}>Можно задавать вопросы подряд — ассистент помнит предыдущий вопрос диалога.</div>
              <div className="quick-links" style={{ marginTop: 12 }}>
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      {turns.map((t, idx) => (
        <TurnView
          key={t.id}
          turn={t}
          index={idx + 1}
          busy={busy}
          onVote={vote}
          onRetry={() => send(t.q)}
        />
      ))}
      <div ref={endRef} />
    </div>
  );
}

/* ---------- Один вопрос врача и ответ ассистента ---------- */
function TurnView({
  turn, index, busy, onVote, onRetry,
}: {
  turn: Turn; index: number; busy: boolean;
  onVote: (t: Turn, v: number) => void; onRetry: () => void;
}) {
  const [repOpen, setRepOpen] = React.useState(false);
  const [repText, setRepText] = React.useState('');
  const [repDone, setRepDone] = React.useState(false);
  const [confTxt, confCls] = confPill(turn.meta?.top_score);
  const streaming = turn.state === 'streaming';

  const sendReport = async () => {
    if (!repText.trim()) return;
    try {
      const ctx = `[сессия ${(turn.meta?.session_id || '').slice(0, 8)}] [score ${turn.meta?.top_score ?? '?'}] ` +
        `Вопрос: ${turn.q.slice(0, 300)} | Ответ: ${turn.a.slice(0, 500)} || Проблема: ${repText.trim()}`;
      await api('/feedback', { method: 'POST', body: JSON.stringify({ query: turn.q, vote: -1, comment: ctx.slice(0, 2000) }) });
      setRepDone(true); setRepOpen(false); setRepText('');
      toast('Сообщение отправлено разработчикам', 'ok');
    } catch (e) {
      toast(humanError(e), 'err');
    }
  };

  return (
    <div className="turn" data-state={turn.state} data-answer-len={turn.a.length}>
      <div className="turn-q">
        <span className="turn-badge" aria-hidden="true">{index}</span>
        <div>
          <div className="turn-q-label caption">Вопрос врача</div>
          <div className="turn-q-text">{turn.q}</div>
        </div>
      </div>

      <Card className="turn-a">
        {streaming && !turn.a && (
          <Skeleton lines={3} label="Готовлю ответ по протоколам" />
        )}

        {turn.state === 'error' && (
          <ErrorBox error={turn.error} onRetry={onRetry} hint="Повторить вопрос можно кнопкой ниже." />
        )}

        {turn.a && (
          <>
            <div className="row turn-meta">
              {(turn.meta?.needs_clarification)
                ? <span className="pill pill-warn">нужно уточнение</span>
                : <span className={confCls}>уверенность: {confTxt}</span>}
              {typeof turn.meta?.top_score === 'number' && <span className="pill pill-mute num">score {turn.meta.top_score.toFixed(2)}</span>}
              {turn.meta?.refused && <span className="pill pill-danger">честный отказ</span>}
              {turn.meta?.cached && <span className="pill pill-mute">из кэша · {turn.meta?.latency_ms} мс</span>}
              {!turn.meta?.cached && turn.meta?.latency_ms != null && <span className="pill pill-mute num">{Math.round(turn.meta.latency_ms)} мс</span>}
              {turn.meta?.doc_count > 1 && <span className="pill pill-mute">синтез из {turn.meta.doc_count} документов</span>}
              {turn.meta?.partial && <span className="pill pill-warn">ответ неполный</span>}
              {turn.state === 'stopped' && <span className="pill pill-warn">остановлено вручную</span>}
            </div>

            {turn.meta?.needs_clarification && (
              <div className="clarify" role="status"><b>Уточните, пожалуйста:</b> {turn.meta.clarifying_question}</div>
            )}

            <div className="answer"><Markdown text={turn.a} />{streaming && <span className="stream-caret" aria-hidden="true" />}</div>

            {!streaming && !turn.meta?.refused && !turn.meta?.needs_clarification && (turn.meta?.top_score ?? 1) < 0.2 && (
              <div className="panel panel-warn" style={{ marginTop: 8 }} role="note">
                <b>Слабое совпадение с базой.</b> Ответ может не опираться на клинические рекомендации — уточните
                запрос (нозология + задача) или откройте раздел «Протоколы».
              </div>
            )}

            {!streaming && (
              <div className="vote-row">
                <CopyButton text={plainText(turn.a)} label="Ответ" />
                <span className="muted">Ответ полезен?</span>
                <button onClick={() => onVote(turn, 1)} disabled={!!turn.voted} aria-label="Ответ полезен">{turn.voted === 1 ? '👍 спасибо!' : '👍'}</button>
                <button onClick={() => onVote(turn, -1)} disabled={!!turn.voted} aria-label="Ответ не полезен">{turn.voted === -1 ? '👎 принято' : '👎'}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setRepOpen(!repOpen); setRepDone(false); }}>Сообщить о проблеме</button>
              </div>
            )}

            {repDone && <p className="panel panel-ok" style={{ marginTop: 8 }}>Спасибо. Сообщение с контекстом экрана отправлено разработчикам.</p>}
            {repOpen && (
              <div className="panel" style={{ marginTop: 8 }}>
                <label className="field">Что не так с этим ответом?
                  <textarea value={repText} onChange={(e) => setRepText(e.target.value)} rows={2}
                    placeholder="Например: неверная дозировка, не тот протокол…" />
                </label>
                <div className="row" style={{ marginTop: 8 }}>
                  <Button onClick={sendReport} disabled={!repText.trim()}>Отправить</Button>
                  <span className="muted">уйдёт вопрос, ответ и оценка — без персональных данных</span>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {turn.sources.length > 0 && (
        <details className="sources">
          <summary>Источники ({turn.sources.length})</summary>
          <div className="src-list">
            {turn.sources.map((s: any, i: number) => (
              <div key={i} className="source-card">
                <div>
                  <span className="src-doc">{s.document || s.title || s.nosology}</span>
                  <span className="src-meta">
                    Раздел: {s.section || '—'} · стр. {Array.isArray(s.page_range) ? s.page_range.join(', ') : (s.page_range ?? '—')}
                  </span>
                </div>
                <span className="pill pill-mute num">{typeof s.score === 'number' ? s.score.toFixed(2) : s.score}</span>
              </div>
            ))}
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <CopyButton
              label="Список источников"
              text={turn.sources.map((s: any) => `${s.document || s.title || s.nosology} — ${s.section || ''}, стр. ${s.page_range ?? ''}`).join('\n')}
            />
          </div>
        </details>
      )}
    </div>
  );
}
