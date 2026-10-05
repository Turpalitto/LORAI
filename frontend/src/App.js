import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import React from 'react';
import { Banner } from './components/common';
import { Dashboard, Chat, ProtocolSearch, DosageCalc, ChecklistPage, Templates, Admin, DiffDx, Referral, History } from './pages/pages';
function route() { return window.location.hash.replace('#/', '') || 'chat'; }
export default function App() {
    const [, tick] = React.useState(0);
    React.useEffect(() => { const f = () => tick(x => x + 1); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f); }, []);
    const r = route();
    return (_jsxs("div", { style: { maxWidth: 960, margin: '0 auto', padding: 20, fontFamily: 'system-ui' }, children: [_jsx(Banner, {}), _jsx("nav", { style: { display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }, children: [['', 'Дашборд'], ['chat', 'Чат'], ['protocols', 'Протоколы'], ['dosage', 'Дозы'], ['diff', 'Дифдиагностика'], ['referral', 'Направление'], ['checklist', 'Чек-лист'], ['templates', 'Шаблоны'], ['history', 'История'], ['admin', 'Админ']].map(([h, l]) => _jsx("a", { href: '#/' + h, children: l }, h)) }), r === '' && _jsx(Dashboard, {}), r === 'chat' && _jsx(Chat, {}), r.startsWith('protocols') && _jsx(ProtocolSearch, {}), r === 'dosage' && _jsx(DosageCalc, {}), r === 'diff' && _jsx(DiffDx, {}), r === 'referral' && _jsx(Referral, {}), r.startsWith('checklist') && _jsx(ChecklistPage, {}), r === 'templates' && _jsx(Templates, {}), r === 'history' && _jsx(History, {}), r === 'admin' && _jsx(Admin, {})] }));
}
