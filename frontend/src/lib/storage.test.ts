import { describe, it, expect, beforeEach } from 'vitest';
import { __resetStoreForTests, store } from './storage';

beforeEach(() => __resetStoreForTests());

describe('хранилище', () => {
  it('пишет и читает значения без localStorage (приватный режим/Node)', () => {
    store.set('k', 'v');
    expect(store.get('k')).toBe('v');
    expect(store.get('missing')).toBeNull();
  });

  it('удаляет значения', () => {
    store.set('k', 'v');
    store.remove('k');
    expect(store.get('k')).toBeNull();
  });

  it('приводит типы с запасным значением', () => {
    store.set('n', '42');
    store.set('b', '1');
    store.set('bad', 'не число');
    expect(store.num('n', 0)).toBe(42);
    expect(store.num('bad', 7)).toBe(7);
    expect(store.num('missing', 5)).toBe(5);
    expect(store.bool('b')).toBe(true);
    expect(store.bool('missing', true)).toBe(true);
  });
});
