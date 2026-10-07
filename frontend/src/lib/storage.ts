/* Безопасный доступ к localStorage.
   В приватном режиме Safari и в webview с отключённым хранилищем обращение
   к localStorage бросает исключение (а не возвращает null) — раньше это
   роняло весь экран при первом же setItem. Здесь единая точка входа с
   деградацией в память процесса, чтобы приложение работало всегда. */

const memory = new Map<string, string>();
let usable: boolean | null = null;

function ls(): Storage | null {
  if (usable === false) return null;
  try {
    const t = '__lorai_probe__';
    window.localStorage.setItem(t, '1');
    window.localStorage.removeItem(t);
    usable = true;
    return window.localStorage;
  } catch {
    usable = false;
    return null;
  }
}

export const store = {
  get(key: string): string | null {
    const b = ls();
    return b ? b.getItem(key) : memory.get(key) ?? null;
  },
  set(key: string, value: string): void {
    memory.set(key, value);
    ls()?.setItem(key, value);
  },
  remove(key: string): void {
    memory.delete(key);
    try { ls()?.removeItem(key); } catch { /* noop */ }
  },
  num(key: string, fallback = 0): number {
    const raw = store.get(key);
    if (raw === null || raw.trim() === '') return fallback;
    const n = Number(raw);
    return Number.isFinite(n) ? n : fallback;
  },
  bool(key: string, fallback = false): boolean {
    const v = store.get(key);
    return v === null ? fallback : v === '1' || v === 'true';
  },
};

/* --- Сброс кэша в тестах/на отладке (не часть публичного API приложения) --- */
export function __resetStoreForTests() {
  memory.clear();
  usable = null;
}
