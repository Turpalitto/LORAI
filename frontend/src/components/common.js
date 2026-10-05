import { jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { api, DISC } from '../api/client';
export function Banner() { return _jsxs("div", { style: { background: '#fef3c7', padding: 10, borderRadius: 8, marginBottom: 12 }, children: ["\u26A0\uFE0F ", DISC] }); }
export function useChat() {
    const [q, setQ] = useState('');
    const [a, setA] = useState('');
    const [loading, setLoading] = useState(false);
    const ask = async () => { setLoading(true); try {
        const r = await api('/chat', { method: 'POST', body: JSON.stringify({ query: q }) });
        setA(r.answer || r.warning || JSON.stringify(r));
    }
    catch (e) {
        setA('Ошибка: ' + e.message);
    } setLoading(false); };
    return { q, setQ, a, ask, loading };
}
