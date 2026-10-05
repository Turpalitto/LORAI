import React from 'react';
import { Banner } from './components/common';
import { Dashboard, Chat, ProtocolSearch, DosageCalc, ChecklistPage, Templates, Admin, DiffDx, Referral, History } from './pages/pages';
function route() { return window.location.hash.replace('#/', '') || 'chat'; }
export default function App() {
  const [, tick] = React.useState(0);
  React.useEffect(() => { const f = () => tick(x => x + 1); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f); }, []);
  const r = route();
  return (<div style={{ maxWidth: 960, margin: '0 auto', padding: 20, fontFamily: 'system-ui' }}>
    <Banner />
    <nav style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
      {[['', 'Дашборд'], ['chat', 'Чат'], ['protocols', 'Протоколы'], ['dosage', 'Дозы'], ['diff', 'Дифдиагностика'], ['referral', 'Направление'], ['checklist', 'Чек-лист'], ['templates', 'Шаблоны'], ['history', 'История'], ['admin', 'Админ']].map(([h, l]) => <a key={h} href={'#/' + h}>{l}</a>)}
    </nav>
    {r === '' && <Dashboard />}{r === 'chat' && <Chat />}{r.startsWith('protocols') && <ProtocolSearch />}{r === 'dosage' && <DosageCalc />}{r === 'diff' && <DiffDx />}{r === 'referral' && <Referral />}{r.startsWith('checklist') && <ChecklistPage />}{r === 'templates' && <Templates />}{r === 'history' && <History />}{r === 'admin' && <Admin />}
  </div>);
}
