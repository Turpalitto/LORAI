import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import React, { useState } from 'react';
import { api } from '../api/client';
export function Dashboard() {
    const [stats, setStats] = useState(null);
    React.useEffect(() => { api('/admin/documents').then(d => setStats({ docs: d.items?.length })).catch(() => api('/protocols?q=').then(d => setStats({ docs: d.items?.length }))); }, []);
    return _jsxs("div", { children: [_jsx("h2", { children: "\u0414\u0430\u0448\u0431\u043E\u0440\u0434" }), _jsxs("p", { children: ["\u0414\u043E\u043A\u0443\u043C\u0435\u043D\u0442\u043E\u0432 \u0432 \u0431\u0430\u0437\u0435: ", stats?.docs ?? '…'] })] });
}
export function Chat() {
    const [q, setQ] = React.useState('Острый средний отит: диагностика и лечение?');
    const [a, setA] = React.useState('');
    const ask = async () => { const r = await api('/chat', { method: 'POST', body: JSON.stringify({ query: q }) }); setA(r.answer || r.warning); };
    return _jsxs("div", { children: [_jsx("h2", { children: "\u0427\u0430\u0442-\u0430\u0441\u0441\u0438\u0441\u0442\u0435\u043D\u0442 (RAG)" }), _jsx("textarea", { value: q, onChange: e => setQ(e.target.value), rows: 3, style: { width: '100%' } }), _jsx("br", {}), _jsx("button", { onClick: ask, children: "\u0421\u043F\u0440\u043E\u0441\u0438\u0442\u044C" }), _jsx("pre", { style: { whiteSpace: 'pre-wrap', background: '#f3f4f6', padding: 12 }, children: a })] });
}
export function ProtocolSearch() {
    const [q, setQ] = React.useState('H66');
    const [items, setItems] = React.useState([]);
    const go = async () => { const r = await api('/protocols?q=' + encodeURIComponent(q)); setItems(r.items || []); };
    React.useEffect(() => { go(); }, []);
    return _jsxs("div", { children: [_jsx("h2", { children: "\u041F\u043E\u0438\u0441\u043A \u043F\u0440\u043E\u0442\u043E\u043A\u043E\u043B\u0430" }), _jsx("input", { value: q, onChange: e => setQ(e.target.value) }), _jsx("button", { onClick: go, children: "\u041D\u0430\u0439\u0442\u0438" }), items.map((p) => _jsxs("div", { style: { border: '1px solid #ddd', margin: 6, padding: 6 }, children: [_jsx("b", { children: p.nosology }), " [", (p.icd10_codes || []).join(', '), "] ", _jsx("a", { href: '#/checklist/' + p.document_id, children: "\u0447\u0435\u043A-\u043B\u0438\u0441\u0442" })] }, p.document_id))] });
}
export function DosageCalc() {
    const [w, setW] = React.useState('20');
    const [m, setM] = React.useState('40');
    const [r, setR] = React.useState(null);
    const go = async () => setR(await api('/dosage', { method: 'POST', body: JSON.stringify({ weight_kg: +w, mg_per_kg: +m }) }));
    return _jsxs("div", { children: [_jsx("h2", { children: "\u041A\u0430\u043B\u044C\u043A\u0443\u043B\u044F\u0442\u043E\u0440 \u0434\u043E\u0437\u0438\u0440\u043E\u0432\u043E\u043A" }), "\u0412\u0435\u0441 (\u043A\u0433): ", _jsx("input", { value: w, onChange: e => setW(e.target.value) }), " \u043C\u0433/\u043A\u0433: ", _jsx("input", { value: m, onChange: e => setM(e.target.value) }), " ", _jsx("button", { onClick: go, children: "\u0420\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u0442\u044C" }), r && _jsxs("p", { children: ["\u0420\u0430\u0437\u043E\u0432\u0430\u044F \u0434\u043E\u0437\u0430: ", _jsxs("b", { children: [r.single_dose_mg, " \u043C\u0433"] }), ". ", r.warning] })] });
}
export function ChecklistPage() {
    const id = window.location.hash.split('/')[2] || '';
    const [c, setC] = React.useState(null);
    React.useEffect(() => { if (id)
        api('/checklist/' + id).then(setC); }, [id]);
    if (!id)
        return _jsx("div", { children: "\u041E\u0442\u043A\u0440\u043E\u0439\u0442\u0435 \u0447\u0435\u043A-\u043B\u0438\u0441\u0442 \u0438\u0437 \u043F\u043E\u0438\u0441\u043A\u0430 \u043F\u0440\u043E\u0442\u043E\u043A\u043E\u043B\u0430." });
    return _jsxs("div", { children: [_jsxs("h2", { children: ["\u0427\u0435\u043A-\u043B\u0438\u0441\u0442 \u043F\u0440\u0438\u0451\u043C\u0430: ", c?.nosology] }), (c?.checklist || []).map((b, i) => _jsxs("div", { children: [_jsx("h4", { children: b.block }), _jsx("ul", { children: b.points.map((p, j) => _jsx("li", { children: _jsxs("label", { children: [_jsx("input", { type: "checkbox" }), " ", p] }) }, j)) })] }, i)), _jsx("button", { onClick: () => window.print(), children: "\u041F\u0435\u0447\u0430\u0442\u044C / PDF" })] });
}
export function DiffDx() {
    const [s, setS] = React.useState('оталгия, лихорадка');
    const [r, setR] = React.useState([]);
    const go = async () => setR((await api('/diff-diagnosis', { method: 'POST', body: JSON.stringify({ symptoms: s.split(/[,\n]/).map(x => x.trim()).filter(Boolean) }) })).ranked || []);
    return _jsxs("div", { children: [_jsx("h2", { children: "\u0414\u0438\u0444\u0444\u0435\u0440\u0435\u043D\u0446\u0438\u0430\u043B\u044C\u043D\u0430\u044F \u0434\u0438\u0430\u0433\u043D\u043E\u0441\u0442\u0438\u043A\u0430" }), "\u0421\u0438\u043C\u043F\u0442\u043E\u043C\u044B (\u0447\u0435\u0440\u0435\u0437 \u0437\u0430\u043F\u044F\u0442\u0443\u044E): ", _jsx("input", { value: s, onChange: e => setS(e.target.value), style: { width: '60%' } }), " ", _jsx("button", { onClick: go, children: "\u0420\u0430\u043D\u0436\u0438\u0440\u043E\u0432\u0430\u0442\u044C" }), r.map((x, i) => _jsxs("div", { style: { border: '1px solid #ddd', margin: 6, padding: 6 }, children: [_jsx("b", { children: x.nosology }), " [", (x.icd10 || []).join(','), "] score=", x.score, " \u2014 \u0441\u043E\u0432\u043F\u0430\u043B\u043E: ", x.matched.join('; ')] }, i))] });
}
export function Referral() {
    const [id, setId] = React.useState('');
    const [crit, setCrit] = React.useState('мастоидит, парез лицевого нерва');
    const [r, setR] = React.useState(null);
    const go = async () => { const ans = {}; crit.split(',').map(x => x.trim()).filter(Boolean).forEach(k => ans[k] = true); setR(await api('/referral-check', { method: 'POST', body: JSON.stringify({ doc_id: id, answers: ans }) })); };
    return _jsxs("div", { children: [_jsx("h2", { children: "\u041A\u0440\u0438\u0442\u0435\u0440\u0438\u0438 \u043D\u0430\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u044F / \u0433\u043E\u0441\u043F\u0438\u0442\u0430\u043B\u0438\u0437\u0430\u0446\u0438\u0438" }), "ID \u043F\u0440\u043E\u0442\u043E\u043A\u043E\u043B\u0430: ", _jsx("input", { value: id, onChange: e => setId(e.target.value), style: { width: '50%' } }), _jsx("br", {}), "\u041A\u0440\u0438\u0442\u0435\u0440\u0438\u0438 (\u0437\u0430\u043F\u044F\u0442\u0430\u044F): ", _jsx("input", { value: crit, onChange: e => setCrit(e.target.value), style: { width: '60%' } }), " ", _jsx("button", { onClick: go, children: "\u041F\u0440\u043E\u0432\u0435\u0440\u0438\u0442\u044C" }), r && _jsx("p", { children: _jsx("b", { children: r.verdict }) })] });
}
export function History() {
    const [h, setH] = React.useState([]);
    React.useEffect(() => { api('/history').then(d => setH(d.items || [])); }, []);
    return _jsxs("div", { children: [_jsx("h2", { children: "\u0418\u0441\u0442\u043E\u0440\u0438\u044F \u0437\u0430\u043F\u0440\u043E\u0441\u043E\u0432" }), h.map((x, i) => _jsxs("div", { style: { borderBottom: '1px solid #eee', padding: 4 }, children: [x.query, " ", _jsxs("i", { children: ["[", x.intent, "]", x.refused ? ' — отказ' : ''] })] }, i))] });
}
export function Templates() {
    const [id, setId] = React.useState('');
    const [t, setT] = React.useState('');
    const go = async (k) => setT((await api(`/templates/${k}/${id}`)).text);
    return _jsxs("div", { children: [_jsx("h2", { children: "\u0428\u0430\u0431\u043B\u043E\u043D\u044B \u0437\u0430\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0439" }), "ID \u043F\u0440\u043E\u0442\u043E\u043A\u043E\u043B\u0430: ", _jsx("input", { value: id, onChange: e => setId(e.target.value) }), " ", _jsx("button", { onClick: () => go('zaklyuchenie'), children: "\u0417\u0430\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435" }), " ", _jsx("button", { onClick: () => go('napravlenie'), children: "\u041D\u0430\u043F\u0440\u0430\u0432\u043B\u0435\u043D\u0438\u0435" }), _jsx("pre", { style: { whiteSpace: 'pre-wrap' }, children: t })] });
}
export function Admin() {
    const [email, setEmail] = React.useState('admin@lorai.local');
    const [pw, setPw] = React.useState('admin123');
    const [docs, setDocs] = React.useState([]);
    const loginGo = async () => { const { login } = await import('../api/client'); const r = await login(email, pw); localStorage.setItem('token', r.token); setDocs((await api('/admin/documents')).items || []); };
    const upload = async (f) => { const fd = new FormData(); fd.append('f', f); const t = localStorage.getItem('token'); const r = await fetch('http://localhost:8000/admin/upload', { method: 'POST', headers: { Authorization: 'Bearer ' + t }, body: fd }); alert(await r.text()); };
    return _jsxs("div", { children: [_jsx("h2", { children: "\u0410\u0434\u043C\u0438\u043D-\u043F\u0430\u043D\u0435\u043B\u044C" }), _jsx("input", { value: email, onChange: e => setEmail(e.target.value) }), _jsx("input", { type: "password", value: pw, onChange: e => setPw(e.target.value) }), _jsx("button", { onClick: loginGo, children: "\u0412\u043E\u0439\u0442\u0438 \u0438 \u043F\u043E\u043A\u0430\u0437\u0430\u0442\u044C \u0434\u043E\u043A\u0443\u043C\u0435\u043D\u0442\u044B" }), _jsx("br", {}), "\u0417\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044C PDF: ", _jsx("input", { type: "file", accept: ".pdf,.txt", onChange: e => e.target.files && upload(e.target.files[0]) }), docs.map((d) => _jsxs("div", { children: [d.nosology, " [", (d.icd10_codes || []).join(','), "] conf=", d.confidence] }, d.document_id))] });
}
