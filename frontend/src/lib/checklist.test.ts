import { describe, it, expect, beforeEach } from 'vitest';
import { clearChecked, isDone, itemKey, progress, readChecked, toggleChecked, totalPoints, writeChecked } from './checklist';
import { __resetStoreForTests } from './storage';

beforeEach(() => __resetStoreForTests());

describe('чек-лист: отметки', () => {
  it('переживают повторное чтение (сохранение в браузере)', () => {
    toggleChecked('doc-1', itemKey(0, 1), true);
    expect(readChecked('doc-1')).toEqual(['0.1']);
    toggleChecked('doc-1', itemKey(2, 0), true);
    expect(readChecked('doc-1').sort()).toEqual(['0.1', '2.0']);
  });

  it('снятие галочки удаляет пункт', () => {
    toggleChecked('doc-1', itemKey(0, 0), true);
    toggleChecked('doc-1', itemKey(0, 0), false);
    expect(readChecked('doc-1')).toEqual([]);
  });

  it('разные протоколы не смешиваются', () => {
    toggleChecked('a', itemKey(0, 0), true);
    expect(readChecked('b')).toEqual([]);
  });

  it('сброс очищает только свой протокол', () => {
    toggleChecked('a', itemKey(0, 0), true);
    clearChecked('a');
    expect(readChecked('a')).toEqual([]);
  });

  it('битые данные не роняют чтение', () => {
    writeChecked('key', []);
    expect(readChecked('broken')).toEqual([]);
  });
});

describe('чек-лист: прогресс', () => {
  const blocks = [{ points: ['a', 'b'] }, { points: ['c'] }];

  it('считает общее число пунктов', () => {
    expect(totalPoints(blocks)).toBe(3);
    expect(totalPoints(undefined)).toBe(0);
    expect(totalPoints([{}, { points: undefined }])).toBe(0);
  });

  it('доля и завершение', () => {
    expect(progress(0, 3)).toBe(0);
    expect(progress(3, 3)).toBe(1);
    expect(progress(5, 3)).toBe(1);
    expect(progress(1, 0)).toBe(0);
    expect(isDone(3, 3)).toBe(true);
    expect(isDone(0, 0)).toBe(false);
  });
});
