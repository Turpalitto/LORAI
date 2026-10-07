import React from 'react';
import { api } from '../api/client';
import { Button, Card, CopyButton, Empty, ErrorBox, PageHeader, Progress, Skeleton, toast } from '../components/common';
import { ArtEmpty } from '../components/illustrations';
import { clearChecked, itemKey, isDone, progress, readChecked, toggleChecked, totalPoints } from '../lib/checklist';
import { useAsync } from './shared';

/** Идентификатор протокола из адреса #/checklist/<id> (без query-хвоста). */
export function checklistIdFromHash(hash: string): string {
  const part = (hash || '').replace(/^#\/?/, '').split('?')[0];
  const seg = part.split('/');
  return seg[0] === 'checklist' ? (seg[1] || '') : '';
}

export function ChecklistPage() {
  const id = checklistIdFromHash(window.location.hash);
  const [checked, setChecked] = React.useState<string[]>(() => readChecked(id));

  React.useEffect(() => { setChecked(readChecked(id)); }, [id]);

  const data = useAsync(() => api('/checklist/' + id), [id], !!id);
  const blocks: any[] = data.data?.checklist || [];
  const total = totalPoints(blocks);
  const done = checked.length;
  const allDone = isDone(done, total);

  const wasAllDone = React.useRef(false);
  React.useEffect(() => {
    if (allDone && total > 0 && !wasAllDone.current) toast('Все пункты чек-листа отмечены — приём можно завершать', 'ok');
    wasAllDone.current = allDone;
  }, [allDone, total]);

  const onToggle = (key: string, on: boolean) => setChecked(toggleChecked(id, key, on));
  const resetAll = () => { clearChecked(id); setChecked([]); toast('Отметки сброшены', 'info'); };
  const checkAll = () => {
    const keys: string[] = [];
    blocks.forEach((b, i) => (b.points || []).forEach((_: string, j: number) => keys.push(itemKey(i, j))));
    keys.forEach((k) => toggleChecked(id, k, true));
    setChecked(keys);
  };

  if (!id) {
    return (
      <div>
        <PageHeader id="chk-title" title="Чек-лист приёма" />
        <Empty hint="Откройте чек-лист из раздела «Клинические рекомендации» — там кнопка «Чек-лист» у каждой нозологии." action={<a className="btn" href="#/protocols">К протоколам</a>} />
      </div>
    );
  }

  const copyAll = blocks
    .map((b, i) => `${b.block}\n` + (b.points || [])
      .map((p: string, j: number) => `  ${checked.includes(itemKey(i, j)) ? '[x]' : '[ ]'} ${p}`)
      .join('\n'))
    .join('\n\n');

  return (
    <div className="checklist-print stagger">
      <PageHeader
        id="chk-title"
        title={`Чек-лист приёма: ${data.data?.nosology ?? '…'}`}
        sub={data.data ? [ (data.data.icd10_codes || []).join(', '), data.data.approval_year ? `КР ${data.data.approval_year}` : '' ].filter(Boolean).join(' · ') : undefined}
      />

      {data.loading && <Skeleton lines={4} label="Загружаю чек-лист" />}
      {data.error && <ErrorBox error={data.error} onRetry={data.reload} />}

      {data.data?.auto_generated && (
        <div className="panel panel-info" role="note">
          <span className="muted">ℹ️ {data.data.source_note}</span>
        </div>
      )}
      {data.data?.needs_source && (
        <div className="panel panel-warn" role="alert">
          В этом протоколе не удалось выделить разделы диагностики — откройте исходный текст КР в разделе «Протоколы»
          и работайте по нему. <a href="#/protocols">К протоколам</a>
        </div>
      )}

      {total > 0 && (
        <Card className="no-print">
          <Progress
            value={done}
            max={total}
            label={`отмечено ${done} из ${total}`}
          />
          <div className="row" style={{ marginTop: 10 }}>
            <Button variant="secondary" onClick={checkAll} disabled={done === total}>Отметить все</Button>
            <Button variant="ghost" onClick={resetAll} disabled={done === 0}>Сбросить отметки</Button>
            <CopyButton text={copyAll} label="Чек-лист текстом" />
            <Button variant="ghost" onClick={() => window.print()}>Печать / PDF</Button>
          </div>
          {allDone && <p className="panel panel-ok" style={{ marginTop: 10, marginBottom: 0 }}>Все пункты отмечены.</p>}
        </Card>
      )}

      {blocks.map((b: any, i: number) => (
        <Card key={i} className="check-block">
          <h4 style={{ marginTop: 0 }}>{b.block}</h4>
          <ul>
            {(b.points || []).map((p: string, j: number) => {
              const key = itemKey(i, j);
              const on = checked.includes(key);
              return (
                <li key={j}>
                  <label className={'check-item' + (on ? ' done' : '')}>
                    <input type="checkbox" checked={on} onChange={(e) => onToggle(key, e.target.checked)} />
                    <span>{p}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        </Card>
      ))}

      {data.data && total === 0 && !data.data.needs_source && <Empty hint="В этом протоколе разделы для чек-листа не распознаны. Откройте исходный текст КР в разделе «Протоколы»." />}
      <p className="caption no-print">Отметки сохраняются в браузере для этого протокола — можно закрыть и вернуться.</p>
    </div>
  );
}
