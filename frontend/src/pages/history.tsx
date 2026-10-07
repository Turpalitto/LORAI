import React from 'react';
import { api } from '../api/client';
import { Card, Empty, ErrorBox, LoginRequired, PageHeader, Skeleton } from '../components/common';
import { ArtEmpty } from '../components/illustrations';
import { chatHref, useAsync, useAuth } from './shared';

export function History() {
  const session = useAuth();
  const [filter, setFilter] = React.useState('');
  const h = useAsync(() => api('/history?limit=50'), [session?.token], !!session);

  const items: any[] = h.data?.items || [];
  const shown = filter.trim()
    ? items.filter((x) => String(x.query).toLowerCase().includes(filter.trim().toLowerCase()))
    : items;
  const refused = items.filter((x) => x.refused).length;

  return (
    <div className="stagger">
      <PageHeader id="hist-title" title="История запросов" sub="Последние обращения в чат — видно, что врачи спрашивают чаще всего." />
      {!session && <LoginRequired what="историю запросов" />}
      {session && (
        <>
          {h.loading && <Skeleton lines={4} label="Загружаю историю" />}
          {h.error && <ErrorBox error={h.error} onRetry={h.reload} hint="История доступна врачу с активной сессией." />}
          {!h.loading && !h.error && items.length === 0 && (
            <Empty hint="Пока пусто — задайте первый вопрос в разделе «Чат»." action={<a className="btn" href="#/chat">Открыть чат</a>} />
          )}
          {items.length > 0 && (
            <Card>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="muted">Всего записей: {items.length} · отказов: {refused}</span>
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Фильтр по тексту вопроса"
                  aria-label="Фильтр истории"
                  style={{ maxWidth: 320 }}
                />
              </div>
            </Card>
          )}
          {shown.map((x: any, i: number) => (
            <a key={i} className="doc-row doc-row-link" href={chatHref(x.query)}>
              <span style={{ flex: '1 1 240px' }}>{x.query}</span>
              <span className="pill pill-mute">{x.intent}</span>
              {x.refused && <span className="pill pill-danger">отказ</span>}
              <span className="muted">повторить →</span>
            </a>
          ))}
          {filter && shown.length === 0 && <p className="muted">По фильтру ничего не найдено.</p>}
        </>
      )}
      {!session && <div className="empty" role="status"><ArtEmpty /><p>История хранится на сервере и доступна после входа.</p></div>}
    </div>
  );
}
