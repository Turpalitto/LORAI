import { describe, it, expect } from 'vitest';
import { parseInline, parseMarkdown, plainText } from './markdown';

describe('markdown: инлайн', () => {
  it('выделяет жирный и код, остальное — текст', () => {
    const parts = parseInline('Доза **45 мг/кг**, максимум `1000 мг`');
    expect(parts.map((p) => p.kind)).toEqual(['text', 'strong', 'text', 'code']);
    expect(parts[1].text).toBe('45 мг/кг');
    expect(parts[3].text).toBe('1000 мг');
  });

  it('не ломается на незакрытой разметке', () => {
    const parts = parseInline('**не закрыт');
    expect(parts).toEqual([{ kind: 'text', text: '**не закрыт' }]);
  });

  it('пустая строка даёт один текстовый фрагмент', () => {
    expect(parseInline('')).toEqual([{ kind: 'text', text: '' }]);
  });
});

describe('markdown: блоки', () => {
  it('разбирает заголовки, списки и абзацы', () => {
    const blocks = parseMarkdown([
      '## Тактика',
      'Антибиотик первой линии:',
      '- амоксициллин',
      '- при аллергии — цефуроксим',
      '1. Оценить тяжесть',
      '2. Назначить терапию',
    ].join('\n'));

    expect(blocks.map((b) => b.kind)).toEqual(['h', 'p', 'ul', 'ol']);
    expect(blocks[0]).toMatchObject({ kind: 'h', level: 3 });
    const ul = blocks[2] as { items: unknown[][] };
    expect(ul.items).toHaveLength(2);
    const ol = blocks[3] as { items: unknown[][] };
    expect(ol.items).toHaveLength(2);
  });

  it('каждая строка без разметки — отдельный абзац (сохраняет переносы)', () => {
    const blocks = parseMarkdown('Первая строка\nВторая строка');
    expect(blocks).toHaveLength(2);
    expect(blocks.every((b) => b.kind === 'p')).toBe(true);
  });

  it('пустой текст — пустой массив', () => {
    expect(parseMarkdown('')).toEqual([]);
    expect(parseMarkdown('\n\n')).toEqual([]);
  });

  it('заголовок первого уровня не становится h1', () => {
    const [b] = parseMarkdown('# Очень важный ответ');
    expect(b).toMatchObject({ kind: 'h', level: 2 });
  });
});

describe('markdown: текст для копирования', () => {
  it('снимает разметку', () => {
    expect(plainText('## Итог\n**Доза** `45 мг/кг`')).toBe('Итог\nДоза 45 мг/кг');
  });
});
