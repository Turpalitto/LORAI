import { describe, it, expect, vi, afterEach } from 'vitest';
import { api, apiStream, ApiError } from './client';

/* Тесты работают на подменённом fetch: реальная сеть не нужна.
   Главный кейс — регресс: кнопка «Остановить» должна обрывать тело ответа
   даже после того, как fetch уже отдал заголовки (иначе поток дочитывался). */

const enc = new TextEncoder();

function sseResponse(events: object[]) {
  let i = 0;
  return new Response(new ReadableStream({
    pull(c) {
      if (i >= events.length) { c.close(); return; }
      c.enqueue(enc.encode('data: ' + JSON.stringify(events[i++]) + '\n\n'));
    },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

afterEach(() => { vi.unstubAllGlobals(); });

describe('apiStream', () => {
  it('разбирает SSE-события по мере поступления', async () => {
    vi.stubGlobal('fetch', async () => sseResponse([
      { type: 'meta', sources: [{ document: 'КР' }] },
      { type: 'token', text: 'Амок' },
      { type: 'token', text: 'сициллин' },
      { type: 'done', answer: 'Амоксициллин' },
    ]));
    const got: string[] = [];
    await apiStream('/chat/stream', { query: 'x' }, (e) => got.push(e.type));
    expect(got).toEqual(['meta', 'token', 'token', 'done']);
  });

  it('склеивает событие, разорванное между чанками', async () => {
    vi.stubGlobal('fetch', async () => {
      const payload = enc.encode('data: {"type":"token","text":"дробь"}\n\n');
      return new Response(new ReadableStream({
        start(c) {
          c.enqueue(payload.slice(0, 12));
          c.enqueue(payload.slice(12));
          c.close();
        },
      }), { status: 200 });
    });
    const got: any[] = [];
    await apiStream('/chat/stream', {}, (e) => got.push(e));
    expect(got).toHaveLength(1);
    expect(got[0]).toMatchObject({ type: 'token', text: 'дробь' });
  });

  it('отмена обрывает поток уже после прихода заголовков (регресс «Остановить»)', async () => {
    const ctrl = new AbortController();
    let pullsAfterAbort = 0;

    vi.stubGlobal('fetch', async (_url: string, opts: any) => {
      const inner: AbortSignal = opts.signal;
      let closed = false;
      let pending = 0;
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(enc.encode('data: {"type":"meta"}\n\n'));
          // Настоящий fetch рвёт тело ответа, когда его сигнал отменён.
          inner.addEventListener('abort', () => {
            closed = true;
            try { c.error(new DOMException('aborted', 'AbortError')); } catch { /* уже закрыт */ }
          });
        },
        async pull(c) {
          if (closed) return;
          pending += 1;
          await new Promise((r) => setTimeout(r, 60));
          if (closed) return;
          pullsAfterAbort += 1;
          c.enqueue(enc.encode('data: {"type":"token","text":"лишнее"}\n\n'));
        },
        cancel() { closed = true; },
      });
      return new Response(body, { status: 200 });
    });

    const events: string[] = [];
    const p = apiStream('/chat/stream', {}, (e) => {
      events.push(e.type);
      if (e.type === 'meta') ctrl.abort();   // врач нажал «Остановить»
    }, ctrl.signal);

    await expect(p).rejects.toThrow();
    expect(events).toEqual(['meta']);
    expect(pullsAfterAbort).toBe(0);
  });

  it('ошибка сервера объясняется человеческим текстом', async () => {
    vi.stubGlobal('fetch', async () => new Response('boom', { status: 500 }));
    await expect(apiStream('/chat/stream', {}, () => {})).rejects.toBeInstanceOf(ApiError);
  });
});

describe('api', () => {
  it('возвращает JSON и подставляет токен в заголовок', async () => {
    const mem = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => mem.get(k) ?? null,
      setItem: (k: string, v: string) => { mem.set(k, String(v)); },
      removeItem: (k: string) => { mem.delete(k); },
      clear: () => mem.clear(),
    });
    mem.set('token', 'test-token');
    let seenAuth = '';
    vi.stubGlobal('fetch', async (_url: string, opts: any) => {
      seenAuth = opts.headers.Authorization || '';
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    await expect(api('/health')).resolves.toEqual({ ok: true });
    expect(seenAuth).toBe('Bearer test-token');
    mem.clear();
  });

  it('превращает 401 в понятный текст', async () => {
    vi.stubGlobal('fetch', async () => new Response('', { status: 401 }));
    await expect(api('/history')).rejects.toMatchObject({ status: 401 });
  });
});
