/* Мини-разбор ответа ассистента в структуру (без HTML и без сторонних
   библиотек — ответ LLM нельзя вставлять как разметку).
   Раньше ответ выводился одним <div> с white-space: pre-wrap: заголовки,
   списки и выделения из модели выглядели как «**звёздочки**». */

export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'code'; text: string };

export type Block =
  | { kind: 'p'; inlines: Inline[] }
  | { kind: 'h'; level: 2 | 3 | 4; inlines: Inline[] }
  | { kind: 'ul'; items: Inline[][] }
  | { kind: 'ol'; items: Inline[][] };

const BULLET = /^\s*(?:[-*•—]|\u2022)\s+(.*)$/;
const ORDERED = /^\s*(\d{1,2})[.)]\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*)$/;

/** Разбор инлайна: **жирный**, `код`, остальное — текст. */
export function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  const rx = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`)/g;
  let last = 0;
  for (const m of src.matchAll(rx)) {
    const i = m.index ?? 0;
    if (i > last) out.push({ kind: 'text', text: src.slice(last, i) });
    const raw = m[0];
    if (raw.startsWith('`')) out.push({ kind: 'code', text: raw.slice(1, -1) });
    else out.push({ kind: 'strong', text: raw.slice(2, -2) });
    last = i + raw.length;
  }
  if (last < src.length) out.push({ kind: 'text', text: src.slice(last) });
  return out.length ? out : [{ kind: 'text', text: src }];
}

/** Разбор текста на блоки. Каждая строка — отдельный абзац (как pre-wrap),
 *  но списки и заголовки становятся настоящими списками и заголовками. */
export function parseMarkdown(src: string): Block[] {
  const lines = (src || '').replace(/\r\n?/g, '\n').split('\n');
  const blocks: Block[] = [];
  let list: { kind: 'ul' | 'ol'; items: Inline[][] } | null = null;

  const flush = () => { if (list) { blocks.push(list); list = null; } };

  for (const line of lines) {
    if (!line.trim()) { flush(); continue; }

    const h = line.match(HEADING);
    if (h) {
      flush();
      const level = Math.min(4, Math.max(2, h[1].length + 1)) as 2 | 3 | 4;
      blocks.push({ kind: 'h', level, inlines: parseInline(h[2].trim()) });
      continue;
    }

    const b = line.match(BULLET);
    if (b) {
      if (!list || list.kind !== 'ul') { flush(); list = { kind: 'ul', items: [] }; }
      list.items.push(parseInline(b[1].trim()));
      continue;
    }

    const o = line.match(ORDERED);
    if (o) {
      if (!list || list.kind !== 'ol') { flush(); list = { kind: 'ol', items: [] }; }
      list.items.push(parseInline(o[2].trim()));
      continue;
    }

    flush();
    blocks.push({ kind: 'p', inlines: parseInline(line.trim()) });
  }
  flush();
  return blocks;
}

/** Текст без разметки — для копирования в буфер и для test-ожиданий. */
export function plainText(src: string): string {
  return (src || '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^#{1,6}\s+/gm, '');
}
