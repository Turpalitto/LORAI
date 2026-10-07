import React from 'react';
import { parseMarkdown, type Inline } from '../lib/markdown';

/* Рендер ответа ассистента: разметку строит parseMarkdown, здесь только
   React-узлы. Никакого dangerouslySetInnerHTML — текст модели не может
   внедрить разметку в интерфейс врача. */

function InlineNodes({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.kind === 'strong' ? <strong key={i}>{p.text}</strong>
          : p.kind === 'code' ? <code key={i} className="md-code">{p.text}</code>
            : <React.Fragment key={i}>{p.text}</React.Fragment>,
      )}
    </>
  );
}

function List({ items, ordered }: { items: Inline[][]; ordered: boolean }) {
  const Tag = ordered ? 'ol' : 'ul';
  return (
    <Tag className="md-list">
      {items.map((parts, i) => (
        <li key={i} className="md-li">
          <span className="md-li-mark" aria-hidden="true">{ordered ? `${i + 1}.` : '•'}</span>
          <span><InlineNodes parts={parts} /></span>
        </li>
      ))}
    </Tag>
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks = React.useMemo(() => parseMarkdown(text), [text]);
  return (
    <div className="md">
      {blocks.map((b, i) => {
        if (b.kind === 'h') {
          const Tag = (b.level === 2 ? 'h3' : b.level === 3 ? 'h4' : 'h5') as 'h3' | 'h4' | 'h5';
          return <Tag key={i} className="md-h"><InlineNodes parts={b.inlines} /></Tag>;
        }
        if (b.kind === 'ul') return <List key={i} items={b.items} ordered={false} />;
        if (b.kind === 'ol') return <List key={i} items={b.items} ordered />;
        return <p key={i} className="md-p"><InlineNodes parts={b.inlines} /></p>;
      })}
    </div>
  );
}
