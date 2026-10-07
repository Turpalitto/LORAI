import React from 'react';
import { api } from '../api/client';
import { Card, Empty, ErrorBox, PageHeader, Button } from '../components/common';
import { ArtOnboarding } from '../components/illustrations';
import { store } from '../lib/storage';
import { chatHash, chatHref, useAsync, useAuth } from './shared';

/* Дашборд: состояние системы, быстрый вопрос, недавние запросы, индекс базы. */
export function Dashboard() {
  const session = useAuth();
  const [onb, setOnb] = React.useState(() => !store.bool('lorai_onb_done'));
  const [dq, setDq] = React.useState('');
  const [filter, setFilter] = React.useState('');

  const health = useAsync(() => api('/health'), []);
  const protocols = useAsync(() => api('/protocols?q='), []);
  const history = useAsync(() => api('/history'), [], !!session);

  const docs = health.data?.documents;
  const llmMode = String(health.data?.llm_mode || '');
  const items: any[] = protocols.data?.items || [];
  const shown = filter.trim()
    ? items.filter((p) =>
      (String(p.nosology) + ' ' + (p.icd10_codes || []).join(' ')).toLowerCase().includes(filter.trim().toLowerCase()))
    : items;

  const closeOnb = () => { store.set('lorai_onb_done', '1'); setOnb(false); };
  const askQuick = (e: React.FormEvent) => {
    e.preventDefault();
    if (dq.trim()) chatHash(dq.trim());
  };

  return (
    <div className="stagger">
      {onb && (
        <div className="panel panel-info onboard" role="status">
          <ArtOnboarding />
          <div>
            <b>Добро пожаловать в ЛОРАИ</b> — помощник по клиническим рекомендациям (ЛОР).
            <ol>
              <li><b>Чат</b> — клинический вопрос, ответ с цитатами протоколов (вопросы можно задавать подряд в одном диалоге).</li>
              <li><b>Протоколы</b> — точная выдача по нозологии/МКБ без ИИ.</li>
              <li><b>Чек-лист</b> — пошаговый приём с отметками, они сохраняются.</li>
              <li><b>Дифдиагностика</b> — ранжирование нозологий и красные флаги.</li>
            </ol>
            <Button variant="secondary" onClick={closeOnb} style={{ marginTop: 8 }}>Понятно, скрыть</Button>
          </div>
        </div>
      )}

      <Card labelledBy="dash-ask">
        <h2 id="dash-ask">Быстрый вопрос</h2>
        <p className="muted">Напишите клинический вопрос — откроется чат, запрос отправится сразу и вернётся с цитатами протоколов.</p>
        <form className="ask-row" onSubmit={askQuick}>
          <input
            value={dq}
            onChange={(e) => setDq(e.target.value)}
            placeholder="Например: Острый средний отит у ребёнка — лечение?"
            aria-label="Быстрый клинический вопрос"
          />
          <Button type="submit" disabled={!dq.trim()}>Спросить</Button>
        </form>
      </Card>

      <div className="stats-grid">
        <div className="stat">
          <span className="stat-v num">{docs ?? '…'}</span>
          <span className="stat-l">клинических рекомендаций в базе</span>
          {typeof health.data?.chunks === 'number' && (
            <span className="stat-note num">{health.data.chunks} фрагментов текста проиндексировано</span>
          )}
        </div>
        <div className="stat">
          <span className="stat-v num">7</span>
          <span className="stat-l">рабочих инструментов: чат, протоколы, дифдиагностика, дозировки, калькуляторы, чек-лист, шаблоны</span>
        </div>
        <div className="stat" aria-label="Статус системы">
          <span className="row" style={{ gap: 6 }}>
            {health.loading && <span className="pill pill-mute">проверяю…</span>}
            {health.error && <span className="pill pill-danger">сервер недоступен</span>}
            {health.data && (llmMode === 'mock' || !llmMode
              ? <span className="pill pill-warn">ИИ: демо-режим</span>
              : <span className="pill pill-ok">ИИ: подключён</span>)}
            {health.data?.ok && <span className="pill pill-ok">сервер: online</span>}
            {health.data?.retrieval?.backend && (
              <span
                className={'pill ' + (/embeddings/.test(health.data.retrieval.backend) ? 'pill-ok' : 'pill-mute')}
                title={health.data.retrieval.note || health.data.retrieval.backend}
              >
                {/embeddings/.test(health.data.retrieval.backend)
                  ? 'поиск: эмбеддинги'
                  : /tfidf/.test(health.data.retrieval.backend) ? 'поиск: TF-IDF' : 'поиск: ' + health.data.retrieval.backend}
              </span>
            )}
          </span>
          <span className="stat-l">
            {llmMode && llmMode !== 'mock'
              ? `модель ${llmMode}${health.data?.avg_latency_ms ? `, средний ответ ${Math.round(health.data.avg_latency_ms)} мс` : ''}`
              : 'включите LLM-ключ в .env для реальных ответов'}
            {health.data?.retrieval?.backend && (
              <>
                <br />
                {health.data.retrieval.vectors_indexed
                  ? `векторный индекс: ${health.data.retrieval.vectors_indexed} фрагментов`
                  : 'векторный индекс: лексический (без эмбеддингов)'}
              </>
            )}
          </span>
        </div>
      </div>
      {health.error && <ErrorBox error={health.error} onRetry={health.reload} hint="Проверьте, запущен ли backend: uvicorn на порту 8000." />}

      <div className="grid-2">
        <Card labelledBy="dash-recent">
          <h3 id="dash-recent" style={{ marginTop: 0 }}>Недавние запросы</h3>
          {!session && <p className="muted" style={{ margin: 0 }}>Войдите — история запросов подтянется. <a href="#/login">Войти</a></p>}
          {session && history.loading && <p className="muted">Загружаю…</p>}
          {session && history.error && <ErrorBox error={history.error} onRetry={history.reload} />}
          {session && history.data && (history.data.items || []).length === 0 && (
            <p className="muted" style={{ margin: 0 }}>Пока пусто — задайте первый вопрос в чате.</p>
          )}
          {session && (history.data?.items || []).slice(0, 4).map((x: any, i: number) => (
            <a key={i} className="doc-row doc-row-link" href={chatHref(x.query)}>
              <span style={{ flex: '1 1 auto' }}>{x.query}</span>
              <span className="pill pill-mute">{x.intent}</span>
              {x.refused && <span className="pill pill-danger">отказ</span>}
            </a>
          ))}
        </Card>

        <Card labelledBy="dash-index">
          <h3 id="dash-index" style={{ marginTop: 0 }}>Протоколы базы ({items.length || '…'})</h3>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Фильтр по нозологии или МКБ"
            aria-label="Фильтр протоколов"
            style={{ marginBottom: 8 }}
          />
          <div className="quick-links tall">
            {shown.map((p: any) => (
              <a key={p.document_id} href={'#/checklist/' + p.document_id} title={(p.icd10_codes || []).join(', ')}>
                {p.nosology}
              </a>
            ))}
          </div>
          {filter && shown.length === 0 && <p className="muted">Ничего не найдено по фильтру.</p>}
        </Card>
      </div>

      <Card labelledBy="dash-start">
        <h2 id="dash-start">Быстрый старт</h2>
        <div className="quick-links">
          <a href="#/chat">Чат-ассистент</a>
          <a href="#/protocols">Клинические рекомендации</a>
          <a href="#/diff">Дифдиагностика</a>
          <a href="#/dosage">Дозировки</a>
          <a href="#/calc">Калькуляторы</a>
          <a href="#/checklist">Чек-лист приёма</a>
        </div>
      </Card>

      {items.length === 0 && !protocols.loading && !protocols.error && (
        <Empty hint="База пуста. Загрузите PDF клинических рекомендаций в разделе «Админ»." />
      )}
    </div>
  );
}
