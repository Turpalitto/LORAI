export const API = (import.meta as any).env.VITE_API_URL || 'http://localhost:8000';
export const APP_VERSION = '1.3.0';
export const DISC =
  'Справочный инструмент для врача. Решение принимает врач. Не вводите персональные данные пациента (ФИО, телефон, паспорт, СНИЛС).';

export class ApiError extends Error {
  status: number;
  human: string;
  constructor(status: number, human: string, detail = '') {
    super(detail ? `${human} (${detail.slice(0, 160)})` : human);
    this.status = status;
    this.human = human;
  }
}

const HUMAN_BY_STATUS: Record<number, string> = {
  400: 'Запрос отклонён. Проверьте введённые данные и попробуйте снова.',
  401: 'Нужна авторизация. Войдите снова — сессия могла закончиться.',
  403: 'Недостаточно прав для этого действия. Обратитесь к администратору.',
  404: 'Данные не найдены. Уточните запрос или идентификатор протокола.',
  409: 'Данные уже изменились. Обновите страницу и повторите.',
  422: 'Проверьте поля формы: часть значений заполнена некорректно.',
  429: 'Слишком много запросов подряд. Подождите минуту и повторите.',
  500: 'Сервер временно недоступен. Попробуйте повторить через минуту.',
  502: 'Сервер временно недоступен. Попробуйте повторить через минуту.',
  503: 'Сервис на обслуживании. Попробуйте позже.',
  504: 'Сервер не ответил вовремя. Попробуйте повторить.',
};

export function humanError(e: unknown): string {
  if (e instanceof ApiError) return e.human;
  if (e instanceof DOMException && e.name === 'AbortError')
    return 'Превышено время ожидания. Проверьте соединение и попробуйте снова.';
  if (e instanceof TypeError)
    return 'Нет соединения с сервером. Проверьте сеть и адрес API, затем повторите.';
  if (e instanceof Error && e.message) {
    if (/Failed to fetch|NetworkError|Load failed/i.test(e.message))
      return 'Нет соединения с сервером. Проверьте сеть и повторите.';
    return e.message.length > 300 ? e.message.slice(0, 300) + '…' : e.message;
  }
  return 'Не удалось выполнить действие. Проверьте соединение и попробуйте снова.';
}

const authHeader = (): Record<string, string> => {
  try {
    const t = localStorage.getItem('token');
    return t ? { Authorization: 'Bearer ' + t } : {};
  } catch {
    return {};
  }
};

/**
 * fetch с таймаутом и общим сигналом отмены (AbortSignal.any есть не везде).
 * Отмена и таймер снимаются не по приходу заголовков, а по завершении чтения
 * тела: иначе для потокового ответа кнопка «Остановить» перестаёт работать —
 * fetch резолвится на заголовках, а тело продолжает качаться.
 */
function startFetch(url: string, opts: RequestInit, timeoutMs: number, outer?: AbortSignal) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  const onAbort = () => ctrl.abort();
  if (outer) {
    if (outer.aborted) ctrl.abort();
    else outer.addEventListener('abort', onAbort, { once: true });
  }
  const cleanup = () => {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onAbort);
  };
  return { res: fetch(url, { ...opts, signal: ctrl.signal }), cleanup };
}

export async function api(path: string, opts: any = {}, timeoutMs = 30000) {
  const { res, cleanup } = startFetch(
    API + path,
    {
      ...opts,
      headers: { 'Content-Type': 'application/json', ...authHeader(), ...(opts.headers || {}) },
    },
    timeoutMs,
  );
  try {
    const r = await res;
    if (!r.ok) {
      const text = await r.text().catch(() => '');
      throw new ApiError(r.status, HUMAN_BY_STATUS[r.status] || 'Не удалось выполнить действие. Попробуйте снова.', text);
    }
    return await r.json();
  } finally {
    cleanup();
  }
}

export const login = (email: string, password: string) =>
  api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });

export type StreamEvent =
  | { type: 'meta'; sources?: any[]; session_id?: string; top_score?: number; [k: string]: any }
  | { type: 'token'; text?: string }
  | { type: 'corrected'; text?: string }
  | { type: 'done'; answer?: string | null; latency_ms?: number; warning?: string; [k: string]: any };

/**
 * Потоковый ответ чата: POST /chat/stream (SSE поверх POST, чтобы клинический
 * текст вопроса не попадал в URL и логи прокси). События разбираются по мере
 * поступления — интерфейс печатает ответ токенами.
 */
export async function apiStream(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
  timeoutMs = 120000,
): Promise<void> {
  const { res, cleanup } = startFetch(
    API + path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authHeader() },
      body: JSON.stringify(body),
    },
    timeoutMs,
    signal,
  );
  try {
    const r = await res;
    if (!r.ok) {
      const text = await r.text().catch(() => '');
      throw new ApiError(r.status, HUMAN_BY_STATUS[r.status] || 'Сервер не принял запрос.', text);
    }
    if (!r.body) throw new ApiError(0, 'Поток недоступен: браузер не поддерживает чтение ответа по частям.');

    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let events = 0;
    const debug = () => {
      try { return localStorage.getItem('lorai_debug_sse') === '1'; } catch { return false; }
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const part of parts) {
        const line = part.split('\n').find((l) => l.startsWith('data: '));
        if (!line) continue;
        let parsed: StreamEvent;
        try { parsed = JSON.parse(line.slice(6)) as StreamEvent; } catch { continue; }
        events++;
        if (debug()) console.info('[sse]', events, parsed.type, signal?.aborted ? 'SIGNAL-ABORTED' : '');
        try {
          onEvent(parsed);
        } catch (err) {
          // Ошибку обработчика нельзя терять: иначе поток выглядит «пустым ответом».
          console.error('[sse] обработчик события упал', parsed.type, err);
        }
      }
    }
    if (debug()) console.info('[sse] конец потока, событий:', events, 'aborted:', !!signal?.aborted);
  } finally {
    cleanup();
  }
}
