import React from 'react';

/* Собственные line-art SVG в палитре приложения (teal #0f766e + slate).
   Декоративные: aria-hidden, рядом всегда есть текстовое описание. */
const C = '#0f766e';
const S = '#94a3b8';
const BG = '#f0fdfa';

function Frame({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div role="img" aria-label={label} style={{ width: 132 }}>
      <svg viewBox="0 0 132 100" width="132" height="100" aria-hidden="true">
        <rect x="4" y="4" width="124" height="92" rx="14" fill={BG} className="art-bg" />
        {children}
      </svg>
    </div>
  );
}

export function ArtSearch() {
  return (
    <Frame label="Иллюстрация: поиск по документу">
      <rect x="30" y="22" width="44" height="56" rx="6" fill="#fff" className="art-paper" stroke={S} strokeWidth="3" />
      <line x1="38" y1="34" x2="66" y2="34" stroke={S} strokeWidth="3" strokeLinecap="round" />
      <line x1="38" y1="43" x2="66" y2="43" stroke={S} strokeWidth="3" strokeLinecap="round" />
      <line x1="38" y1="52" x2="56" y2="52" stroke={S} strokeWidth="3" strokeLinecap="round" />
      <circle cx="82" cy="60" r="14" fill="#fff" className="art-paper" stroke={C} strokeWidth="4" />
      <line x1="92" y1="70" x2="102" y2="80" stroke={C} strokeWidth="5" strokeLinecap="round" />
    </Frame>
  );
}

export function ArtChat() {
  return (
    <Frame label="Иллюстрация: консультация ассистента">
      <path d="M28 24 h60 a8 8 0 0 1 8 8 v28 a8 8 0 0 1 -8 8 H56 l-14 12 v-12 h-14 a8 8 0 0 1 -8 -8 V32 a8 8 0 0 1 8 -8 z" fill="#fff" className="art-paper" stroke={S} strokeWidth="3" />
      <path d="M52 44 h12 M58 38 v12" stroke={C} strokeWidth="4" strokeLinecap="round" />
      <circle cx="78" cy="52" r="4" fill={C} />
    </Frame>
  );
}

export function ArtEmpty() {
  return (
    <Frame label="Иллюстрация: пока пусто">
      <path d="M30 40 h56 v30 a6 6 0 0 1 -6 6 H36 a6 6 0 0 1 -6 -6 z" fill="#fff" className="art-paper" stroke={S} strokeWidth="3" />
      <path d="M30 40 l10 -12 h40 l6 12" fill="none" stroke={S} strokeWidth="3" strokeLinejoin="round" />
      <path d="M52 58 l8 8 14 -16" fill="none" stroke={C} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </Frame>
  );
}

export function ArtOnboarding() {
  return (
    <Frame label="Иллюстрация: помощник врача">
      <circle cx="66" cy="42" r="20" fill="#fff" className="art-paper" stroke={C} strokeWidth="4" />
      <path d="M58 42 h16 M66 34 v16" stroke={C} strokeWidth="4" strokeLinecap="round" />
      <path d="M40 84 q26 -18 52 0" fill="none" stroke={S} strokeWidth="3" strokeLinecap="round" />
    </Frame>
  );
}
