/* Состояние чек-листа приёма: пока врач идёт по пунктам, галочки должны
   переживать перезагрузку и переход между разделами (раньше сбрасывались). */
import { store } from './storage';

const PREFIX = 'lorai-check:';

export const itemKey = (blockIndex: number, pointIndex: number): string => `${blockIndex}.${pointIndex}`;

export function readChecked(docId: string): string[] {
  if (!docId) return [];
  const raw = store.get(PREFIX + docId);
  if (!raw) return [];
  try {
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export function writeChecked(docId: string, keys: string[]): void {
  if (!docId) return;
  if (keys.length === 0) store.remove(PREFIX + docId);
  else store.set(PREFIX + docId, JSON.stringify(keys));
}

export function toggleChecked(docId: string, key: string, on: boolean): string[] {
  const set = new Set(readChecked(docId));
  if (on) set.add(key); else set.delete(key);
  const next = [...set];
  writeChecked(docId, next);
  return next;
}

export function clearChecked(docId: string): void {
  writeChecked(docId, []);
}

/** Сколько всего пунктов в чек-листе (по ответу /checklist). */
export function totalPoints(checklist: { points?: string[] }[] | undefined): number {
  return (checklist || []).reduce((n, b) => n + (b.points?.length || 0), 0);
}

/** Доля выполненных пунктов 0..1 — для полосы прогресса. */
export function progress(checked: number, total: number): number {
  if (!total) return 0;
  return Math.min(1, Math.max(0, checked / total));
}

export const isDone = (checked: number, total: number): boolean => total > 0 && checked >= total;
