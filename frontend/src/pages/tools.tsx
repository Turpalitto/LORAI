import React from 'react';
import { api, humanError } from '../api/client';
import { Button, Card, CopyButton, Empty, ErrorBox, PageHeader, Skeleton, toast } from '../components/common';
import { chatHash, useAsync } from './shared';

/* ---------- Дозировки ---------- */
export function DosageCalc() {
  const [w, setW] = React.useState('20');
  const [m, setM] = React.useState('45');
  const [max, setMax] = React.useState('1000');
  const [freq, setFreq] = React.useState('');
  const [r, setR] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const weight = Number(w.replace(',', '.'));
  const perKg = Number(m.replace(',', '.'));
  const maxMg = max.trim() ? Number(max.replace(',', '.')) : undefined;
  const valid =
    Number.isFinite(weight) && weight > 0 && weight < 300 &&
    Number.isFinite(perKg) && perKg > 0 && perKg < 1000 &&
    (maxMg === undefined || (Number.isFinite(maxMg) && maxMg > 0));

  const go = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!valid) { setErr('Проверьте числа: вес 0–300 кг, доза 0–1000 мг/кг, максимум больше нуля.'); return; }
    setBusy(true); setErr(''); setR(null);
    try {
      setR(await api('/dosage', {
        method: 'POST',
        body: JSON.stringify({ weight_kg: weight, mg_per_kg: perKg, max_mg: maxMg, frequency: freq }),
      }));
    } catch (e2) {
      setErr(humanError(e2));
    }
    setBusy(false);
  };

  const limited = r && r.max_mg != null && Math.abs((r.weight_kg * r.mg_per_kg) - r.single_dose_mg) > 0.05;

  return (
    <div className="stagger">
      <PageHeader id="dose-title" title="Калькулятор дозировок" sub="Арифметика дозы по весу. Значения мг/кг берите из клинической рекомендации — калькулятор их не подставляет." />
      <Card labelledBy="dose-title">
        <form className="form-line" onSubmit={go}>
          <label className="field" style={{ flex: '1 1 150px' }}>
            Вес, кг
            <input value={w} onChange={(e) => setW(e.target.value)} inputMode="decimal" aria-label="Вес, кг" />
          </label>
          <label className="field" style={{ flex: '1 1 150px' }}>
            Доза, мг/кг
            <input value={m} onChange={(e) => setM(e.target.value)} inputMode="decimal" aria-label="Доза, мг/кг" />
          </label>
          <label className="field" style={{ flex: '1 1 150px' }}>
            Максимум, мг (необязательно)
            <input value={max} onChange={(e) => setMax(e.target.value)} inputMode="decimal" aria-label="Максимальная доза, мг" />
          </label>
          <label className="field" style={{ flex: '1 1 180px' }}>
            Кратность приёма (текстом)
            <input value={freq} onChange={(e) => setFreq(e.target.value)} placeholder="например: 2 раза в день" aria-label="Кратность приёма" />
          </label>
          <Button type="submit" loading={busy} disabled={!valid}>Рассчитать</Button>
        </form>
        {!valid && <p className="caption" style={{ marginTop: 6 }}>Заполните вес и дозу положительными числами.</p>}
        {err && <div className="error-box" role="alert" style={{ marginTop: 10 }}>{err}</div>}
      </Card>

      {r && (
        <div className="panel panel-ok" role="status">
          Разовая доза: <b className="num" style={{ fontSize: 21 }}>{r.single_dose_mg} мг</b>
          {limited && <span className="pill pill-warn" style={{ marginLeft: 8 }}>ограничено максимумом {r.max_mg} мг</span>}
          <p className="muted" style={{ margin: '6px 0 0' }}>
            {r.weight_kg} кг × {r.mg_per_kg} мг/кг{r.frequency ? ` · ${r.frequency}` : ''}
          </p>
          <p className="muted" style={{ margin: '4px 0 0' }}>{r.warning}</p>
          <div className="row" style={{ marginTop: 10 }}>
            <CopyButton label="Расчёт" text={`Разовая доза: ${r.single_dose_mg} мг (${r.weight_kg} кг × ${r.mg_per_kg} мг/кг${r.max_mg ? `, максимум ${r.max_mg} мг` : ''}${r.frequency ? `, ${r.frequency}` : ''})`} />
            <Button variant="ghost" onClick={() => chatHash(`Дозировка при весе ${r.weight_kg} кг: ${freq || 'уточнить кратность'} — что говорит протокол?`)}>Спросить в чате</Button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Калькуляторы ---------- */
export function Calculators() {
  const [fever, setFever] = React.useState(false);
  const [exudate, setExudate] = React.useState(false);
  const [nodes, setNodes] = React.useState(false);
  const [noCough, setNoCough] = React.useState(false);
  const [age, setAge] = React.useState('15-44');
  const [centor, setCentor] = React.useState<any>(null);
  const [pta, setPta] = React.useState(['20', '20', '25', '15']);
  const [ptaR, setPtaR] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const goCentor = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setErr(''); setBusy(true);
    try {
      setCentor(await api('/calculators/centor', { method: 'POST', body: JSON.stringify({ fever, exudate, nodes, no_cough: noCough, age_band: age }) }));
    } catch (e2) { setErr(humanError(e2)); }
    setBusy(false);
  };
  const goPta = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const values = pta.map((v) => Number(v.replace(',', '.')));
    if (values.some((v) => !Number.isFinite(v) || v < -10 || v > 130)) {
      setErr('Пороги слуха — числа от −10 до 130 дБ.'); return;
    }
    setErr(''); setBusy(true);
    try {
      setPtaR(await api('/calculators/pta', { method: 'POST', body: JSON.stringify({ thresholds_db: values }) }));
    } catch (e2) { setErr(humanError(e2)); }
    setBusy(false);
  };

  return (
    <div className="stagger">
      <PageHeader id="calc-title" title="Клинические калькуляторы" sub="Чистые формулы по опубликованным шкалам, без ИИ. Решение всегда за врачом." />
      {err && <div className="error-box" role="alert">{err}</div>}

      <Card labelledBy="calc-centor">
        <h3 id="calc-centor" style={{ marginTop: 0 }}>Шкала Centor/McIsaac (фарингит)</h3>
        <form onSubmit={goCentor}>
          <div style={{ display: 'grid', gap: 6, maxWidth: 520 }}>
            <label className="check"><input type="checkbox" checked={fever} onChange={(e) => setFever(e.target.checked)} /> Температура ≥38 °C</label>
            <label className="check"><input type="checkbox" checked={exudate} onChange={(e) => setExudate(e.target.checked)} /> Налёт/экссудат на миндалинах</label>
            <label className="check"><input type="checkbox" checked={nodes} onChange={(e) => setNodes(e.target.checked)} /> Болезненные шейные лимфоузлы</label>
            <label className="check"><input type="checkbox" checked={noCough} onChange={(e) => setNoCough(e.target.checked)} /> Кашля нет</label>
          </div>
          <div className="form-line" style={{ marginTop: 10 }}>
            <select value={age} onChange={(e) => setAge(e.target.value)} aria-label="Возрастная группа">
              <option value="3-14">3–14 лет</option>
              <option value="15-44">15–44 года</option>
              <option value="45+">45 лет и старше</option>
            </select>
            <Button type="submit" loading={busy}>Посчитать</Button>
          </div>
        </form>
        {centor && (
          <div className="panel panel-ok" style={{ marginTop: 10 }} role="status">
            Баллов: <b className="num">{centor.score} из {centor.max}</b> — {centor.interpretation}
            <p className="muted" style={{ margin: '4px 0 0' }}>{centor.recommendation}</p>
            <div className="row" style={{ marginTop: 8 }}>
              <CopyButton label="Результат" text={`Centor/McIsaac: ${centor.score}/${centor.max} — ${centor.interpretation}. ${centor.recommendation}`} />
            </div>
          </div>
        )}
      </Card>

      <Card labelledBy="calc-pta">
        <h3 id="calc-pta" style={{ marginTop: 0 }}>Средний порог слуха PTA (0.5/1/2/4 кГц, дБ)</h3>
        <form className="form-line" onSubmit={goPta}>
          {pta.map((v, i) => (
            <input
              key={i}
              className="freq-input num"
              value={v}
              onChange={(e) => { const c = [...pta]; c[i] = e.target.value; setPta(c); }}
              inputMode="numeric"
              aria-label={`Порог ${['0.5', '1', '2', '4'][i]} кГц, дБ`}
            />
          ))}
          <Button type="submit" loading={busy}>Посчитать</Button>
          <Button variant="ghost" type="button" onClick={() => { setPta(['20', '20', '25', '15']); setPtaR(null); }}>Сбросить</Button>
        </form>
        {ptaR && (
          <div className="panel panel-ok" style={{ marginTop: 10 }} role="status">
            Среднее: <b className="num" style={{ fontSize: 19 }}>{ptaR.average_db} дБ</b> — {ptaR.grade}
            <p className="muted" style={{ margin: '4px 0 0' }}>{ptaR.recommendation}</p>
            <div className="row" style={{ marginTop: 8 }}>
              <CopyButton label="Результат" text={`PTA: ${ptaR.average_db} дБ — ${ptaR.grade}. ${ptaR.recommendation}`} />
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ---------- Дифдиагностика ---------- */
const EXAMPLES = ['оталгия, лихорадка', 'тризм, боль при глотании', 'заложенность носа, гнойные выделения', 'снижение слуха, шум в ухе'];

export function DiffDx() {
  const [s, setS] = React.useState('оталгия, лихорадка');
  const [r, setR] = React.useState<any[]>([]);
  const [why, setWhy] = React.useState('');
  const [expl, setExpl] = React.useState('');
  const [flags, setFlags] = React.useState<any[]>([]);
  const [ran, setRan] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState('');

  const go = async (e?: React.FormEvent, text?: string) => {
    e?.preventDefault();
    const value = (text ?? s).trim();
    const symptoms = value.split(/[,\n;]/).map((x) => x.trim()).filter(Boolean);
    if (symptoms.length === 0) { setErr('Введите хотя бы один симптом.'); return; }
    setLoading(true); setErr('');
    try {
      const j = await api('/diff-diagnosis', { method: 'POST', body: JSON.stringify({ symptoms }) });
      const ranked = j.ranked || [];
      setR(ranked); setRan(true);
      setWhy(ranked[0]?.why_first || '');
      setExpl(ranked[0]?.explanation || '');
      setFlags(j.red_flags || []);
    } catch (e2) { setErr(humanError(e2)); }
    setLoading(false);
  };

  return (
    <div className="stagger">
      <PageHeader id="dd-title" title="Дифференциальная диагностика" sub="Ранжирование нозологий по симптомам и проверка красных флагов. Не диагноз — подсказка, куда смотреть." />
      <Card labelledBy="dd-title">
        <form className="form-line" onSubmit={go}>
          <input value={s} onChange={(e) => setS(e.target.value)} aria-label="Симптомы" placeholder="Симптомы через запятую" />
          <Button type="submit" loading={loading}>{loading ? 'Анализирую…' : 'Ранжировать'}</Button>
        </form>
        <div className="quick-links" style={{ marginTop: 8 }}>
          {EXAMPLES.map((x) => <button key={x} className="chip" onClick={() => { setS(x); go(undefined, x); }}>{x}</button>)}
        </div>
        {err && <div className="error-box" role="alert" style={{ marginTop: 10 }}>{err}</div>}
      </Card>

      {flags.length > 0 && (
        <div className="panel panel-danger" role="alert">
          <b>🚨 Красные флаги — срочно к врачу (не диагноз, а повод):</b>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {flags.map((f: any) => <li key={f.id} style={{ margin: '3px 0' }}><b>{f.sign}.</b> {f.action}</li>)}
          </ul>
        </div>
      )}
      {ran && flags.length === 0 && (
        <div className="panel panel-ok" role="note">Красных флагов по введённым симптомам не выявлено — продолжайте по протоколу.</div>
      )}

      {loading && r.length === 0 && <Skeleton lines={4} label="Сопоставляю с протоколами" />}
      {ran && r.length === 0 && !loading && <Empty hint="Ни одно совпадение не набрало вес. Опишите симптомы конкретнее (локализация, длительность, температура)." />}

      {why && (
        <div className="panel panel-info">
          <b>🩺 Почему на первом месте:</b> {why}
          {expl && <p className="muted" style={{ margin: '6px 0 0' }}>{expl}</p>}
        </div>
      )}

      {r.map((x: any, i: number) => (
        <div key={i} className={'rank-card' + (i === 0 ? ' top' : '')}>
          <span className="rank-num">{i + 1}</span>
          <span className="rank-name">
            {x.nosology} {(x.icd10 || []).map((c: string) => <span key={c} className="icd" style={{ marginLeft: 6 }}>{c}</span>)}
          </span>
          <span className="score-bar" title={'score ' + x.score}><i style={{ width: Math.min(100, Math.round((x.score ?? 0) * 100)) + '%' }} /></span>
          <span className="rank-sub">совпало: {(x.matched || []).join('; ') || '—'}</span>
          <span className="match-chips">{(x.key_signs || []).map((k: string) => <span key={k}>{k}</span>)}</span>
          <span className="rank-actions">
            <Button variant="ghost" onClick={() => chatHash(`Нозология «${x.nosology}»: тактика, обследование и лечение по протоколу`)}>Спросить в чате</Button>
          </span>
        </div>
      ))}

      {r.length > 0 && (
        <div className="row">
          <CopyButton label="Ранжирование" text={r.map((x, i) => `${i + 1}. ${x.nosology} [${(x.icd10 || []).join(', ')}] — совпало: ${(x.matched || []).join('; ')}`).join('\n')} />
        </div>
      )}
    </div>
  );
}

/* ---------- Направление / госпитализация ---------- */
export function Referral() {
  const docs = useAsync(() => api('/protocols?q='), []);
  const [id, setId] = React.useState('');
  const [crit, setCrit] = React.useState('');
  const [r, setR] = React.useState<any>(null);
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const list: any[] = docs.data?.items || [];
  const criteria = crit.split(/[,\n;]/).map((x) => x.trim()).filter(Boolean);

  const go = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!id) { setErr('Выберите протокол из списка.'); return; }
    if (criteria.length === 0) { setErr('Укажите хотя бы один критерий из протокола.'); return; }
    setErr(''); setBusy(true);
    try {
      const answers: Record<string, boolean> = {};
      criteria.forEach((k) => { answers[k] = true; });
      setR(await api('/referral-check', { method: 'POST', body: JSON.stringify({ doc_id: id, answers }) }));
    } catch (e2) { setErr(humanError(e2)); }
    setBusy(false);
  };

  return (
    <div className="stagger">
      <PageHeader id="ref-title" title="Критерии направления / госпитализации" sub="Отметьте критерии, которые есть у пациента, — ЛОРАИ проверит их по выбранному протоколу." />
      <Card labelledBy="ref-title">
        <form onSubmit={go}>
          <label className="field">
            Протокол
            <select value={id} onChange={(e) => setId(e.target.value)} aria-label="Протокол">
              <option value="">— выберите протокол —</option>
              {list.map((d: any) => (
                <option key={d.document_id} value={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(', ')}]</option>
              ))}
            </select>
          </label>
          <label className="field" style={{ marginTop: 10 }}>
            Критерии из текста КР (через запятую или с новой строки)
            <textarea value={crit} onChange={(e) => setCrit(e.target.value)} rows={2}
              placeholder="например: мастоидит, парез лицевого нерва, внутричерепные осложнения" />
          </label>
          {criteria.length > 0 && (
            <p className="caption" style={{ marginTop: 6 }}>Отмечено критериев: {criteria.length}</p>
          )}
          <div className="row" style={{ marginTop: 10 }}>
            <Button type="submit" loading={busy}>Проверить</Button>
            <Button variant="ghost" type="button" onClick={() => { setCrit('мастоидит, парез лицевого нерва'); setR(null); }}>Пример</Button>
          </div>
        </form>
        {docs.error && <ErrorBox error={docs.error} onRetry={docs.reload} />}
        {!docs.loading && list.length === 0 && !docs.error && <p className="muted">Список протоколов недоступен (нужен запуск backend).</p>}
        {err && <div className="error-box" role="alert" style={{ marginTop: 10 }}>{err}</div>}
      </Card>

      {r && (
        <div className={'panel ' + (r.referral_needed ? 'panel-warn' : 'panel-ok')} role="status">
          <b>{r.verdict}</b>
          {r.protocol && <p className="muted" style={{ margin: '6px 0 0' }}>Протокол: {r.protocol}</p>}
          {(r.positive_criteria || []).length > 0 && (
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {(r.positive_criteria || []).map((c: string) => <li key={c}>{c}</li>)}
            </ul>
          )}
          <div className="row" style={{ marginTop: 8 }}>
            <CopyButton label="Вердикт" text={`${r.verdict} Критерии: ${(r.positive_criteria || []).join(', ') || '—'}. Протокол: ${r.protocol || ''}`} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------- Шаблоны заключений ---------- */
export function Templates() {
  const docs = useAsync(() => api('/protocols?q='), []);
  const [id, setId] = React.useState('');
  const [t, setT] = React.useState('');
  const [kind, setKind] = React.useState('');
  const [err, setErr] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const list: any[] = docs.data?.items || [];

  const go = async (k: string) => {
    if (!id) { setErr('Сначала выберите протокол из списка.'); return; }
    setErr(''); setBusy(true);
    try { setT((await api(`/templates/${k}/${id}`)).text); setKind(k); }
    catch (e) { setErr(humanError(e)); }
    setBusy(false);
  };

  return (
    <div className="stagger">
      <PageHeader id="tpl-title" title="Шаблоны заключений" sub="Заготовка документа с подстановкой нозологии, МКБ и года КР — дальше правит врач." />
      <Card labelledBy="tpl-title">
        <div className="form-line">
          <select value={id} onChange={(e) => setId(e.target.value)} aria-label="Протокол">
            <option value="">— выберите протокол —</option>
            {list.map((d: any) => <option key={d.document_id} value={d.document_id}>{d.nosology} [{(d.icd10_codes || []).join(', ')}]</option>)}
          </select>
          <Button onClick={() => go('zaklyuchenie')} loading={busy}>Заключение</Button>
          <Button variant="secondary" onClick={() => go('napravlenie')} loading={busy}>Направление</Button>
        </div>
        {docs.error && <ErrorBox error={docs.error} onRetry={docs.reload} />}
        {err && <div className="error-box" role="alert" style={{ marginTop: 10 }}>{err}</div>}
      </Card>

      {!t && !err && !busy && <p className="muted">Выберите протокол и тип документа — текст появится здесь, готовый к копированию и печати.</p>}
      {busy && !t && <Skeleton lines={5} label="Готовлю шаблон" />}
      {t && (
        <>
          <pre className="template-pre">{t}</pre>
          <div className="row">
            <CopyButton label="Текст шаблона" text={t} small={false} />
            <Button variant="ghost" onClick={() => window.print()}>Печать / PDF</Button>
            {kind && <span className="muted">тип: {kind === 'zaklyuchenie' ? 'заключение' : 'направление'}</span>}
          </div>
        </>
      )}
    </div>
  );
}
