import React from 'react';
import { api } from '../api/client';
import { Button, Card, Empty, ErrorBox, LoginRequired, PageHeader, Skeleton, toast } from '../components/common';
import { ArtSearch } from '../components/illustrations';
import { chatHash, useAsync, useAuth } from './shared';

/* Поиск протокола по нозологии/МКБ + похожие + избранное. */
export function ProtocolSearch() {
  const session = useAuth();
  const [q, setQ] = React.useState('H66');
  const [query, setQuery] = React.useState('H66');
  const [rel, setRel] = React.useState<Record<string, any[] | 'loading'>>({});

  const search = useAsync(() => api('/protocols?q=' + encodeURIComponent(query)), [query]);
  const favs = useAsync(() => api('/favorites'), [], !!session);
  const items: any[] = search.data?.items || [];
  const favItems: any[] = favs.data?.items || [];
  const favIds = new Set(favItems.map((f) => f.doc_id));
  const nameOf = (docId: string) =>
    favItems.find((f) => f.doc_id === docId)?.nosology
    || items.find((i) => i.document_id === docId)?.nosology
    || docId;

  /* Живой поиск: не дёргаем сервер на каждый символ. */
  React.useEffect(() => {
    const t = setTimeout(() => setQuery(q), 350);
    return () => clearTimeout(t);
  }, [q]);

  const toggleRelated = async (id: string) => {
    if (rel[id]) {
      const c = { ...rel }; delete c[id]; setRel(c);
      return;
    }
    setRel({ ...rel, [id]: 'loading' });
    try {
      const r = await api('/protocols/' + id + '/related');
      setRel((prev) => ({ ...prev, [id]: r.items || [] }));
    } catch (e) {
      setRel((prev) => { const c = { ...prev }; delete c[id]; return c; });
      toast('Не удалось загрузить похожие протоколы', 'err');
    }
  };

  const addFav = async (docId: string) => {
    try {
      await api('/favorites', { method: 'POST', body: JSON.stringify({ doc_id: docId }) });
      toast('Добавлено в избранное', 'ok');
      favs.reload();
    } catch {
      toast('Избранное требует входа — войдите в разделе «Вход»', 'err');
    }
  };
  const delFav = async (id: number) => {
    try {
      await api('/favorites/' + id, { method: 'DELETE' });
      toast('Удалено из избранного', 'ok');
      favs.reload();
    } catch {
      toast('Не удалось удалить из избранного', 'err');
    }
  };

  return (
    <div className="stagger">
      <PageHeader id="proto-title" title="Клинические рекомендации" sub="Точный поиск по базе без ИИ: нозология, код МКБ или ключевое слово." />

      <Card labelledBy="proto-title">
        <form className="form-line" onSubmit={(e) => { e.preventDefault(); setQuery(q); }}>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Нозология или код МКБ"
            placeholder="Код МКБ или название, например H66"
          />
          <Button type="submit" loading={search.loading}>Найти</Button>
        </form>
        <p className="caption" style={{ marginTop: 6 }}>
          {items.length > 0 && !search.loading ? `Найдено протоколов: ${items.length}` : 'Поиск идёт по загруженным клиническим рекомендациям.'}
        </p>
      </Card>

      {search.loading && <Skeleton lines={3} label="Ищу в базе" />}
      {search.error && <ErrorBox error={search.error} onRetry={search.reload} />}
      {!search.loading && !search.error && items.length === 0 && (
        <Empty
          hint="Ничего не найдено. Попробуйте код МКБ (например, H66) или другое название нозологии — точный поиск работает и без ИИ."
          action={<Button variant="secondary" onClick={() => { setQ(''); setQuery(''); }}>Сбросить запрос</Button>}
        />
      )}

      {items.map((p: any) => (
        <Card key={p.document_id} className="proto-card">
          <div className="doc-row proto-row">
            <div className="proto-head">
              <b>{p.nosology}</b>
              <span className="row" style={{ gap: 4 }}>
                {(p.icd10_codes || []).map((c: string) => <span key={c} className="icd">{c}</span>)}
              </span>
            </div>
            <a className="btn btn-sm btn-secondary" href={'#/checklist/' + p.document_id}>Чек-лист</a>
            <Button variant="ghost" onClick={() => chatHash(`Что говорит протокол по нозологии «${p.nosology}»?`)}>Спросить в чате</Button>
            <Button variant="ghost" onClick={() => toggleRelated(p.document_id)}>
              {rel[p.document_id] ? 'Скрыть похожие' : 'Похожие'}
            </Button>
            {session && (
              favIds.has(p.document_id)
                ? <span className="pill pill-ok">в избранном</span>
                : <Button variant="ghost" onClick={() => addFav(p.document_id)} aria-label={`Добавить «${p.nosology}» в избранное`}>★ В избранное</Button>
            )}
          </div>
          {rel[p.document_id] === 'loading' && <p className="muted" style={{ marginTop: 8 }}>Ищу похожие протоколы…</p>}
          {Array.isArray(rel[p.document_id]) && (
            <div className="doc-extra">
              {(rel[p.document_id] as any[]).length === 0
                ? <p className="muted" style={{ margin: 0 }}>Похожих протоколов не найдено.</p>
                : (
                  <ul className="related-list">
                    {(rel[p.document_id] as any[]).map((r: any) => (
                      <li key={r.document_id}>
                        <a href={'#/checklist/' + r.document_id}>{r.nosology}</a>
                        <span className="muted"> [{(r.icd10_codes || []).join(', ')}]</span>
                        {(r.reasons || []).length > 0 && <div className="caption">{(r.reasons || []).join('; ')}</div>}
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          )}
        </Card>
      ))}

      <h3>⭐ Моё избранное</h3>
      {!session && <LoginRequired what="избранное" />}
      {session && favs.loading && <Skeleton lines={2} label="Загружаю избранное" />}
      {session && favs.error && <ErrorBox error={favs.error} onRetry={favs.reload} />}
      {session && !favs.loading && !favs.error && favItems.length === 0 && (
        <p className="muted">Пока пусто — отметьте нужные протоколы звёздочкой, они появятся здесь.</p>
      )}
      {session && favItems.map((f: any) => (
        <div key={f.id} className="doc-row">
          <b>{f.nosology || nameOf(f.doc_id)}</b>
          {(f.icd10_codes || []).length > 0 && (f.icd10_codes || []).map((c: string) => <span key={c} className="icd">{c}</span>)}
          {f.note && <i className="muted">({f.note})</i>}
          <a className="btn btn-sm btn-secondary" href={'#/checklist/' + f.doc_id}>Чек-лист</a>
          <Button variant="ghost" onClick={() => delFav(f.id)} aria-label={`Убрать «${f.nosology || f.doc_id}» из избранного`}>✕ Убрать</Button>
        </div>
      ))}
    </div>
  );
}
