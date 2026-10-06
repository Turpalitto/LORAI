export const API = (import.meta as any).env.VITE_API_URL || 'http://localhost:8000';
export const APP_VERSION = '1.1.0';
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
  422: 'Проверьте поля формы: часть значений заполнена некорректно.',
  429: 'Слишком много запросов подряд. Подождите минуту и повторите.',
  500: 'Сервер временно недоступен. Попробуйте повторить через минуту.',
  502: 'Сервер временно недоступен. Попробуйте повторить через минуту.',
  503: 'Сервис на обслуживании. Попробуйте позже.',
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

export async function api(path: string, opts: any = {}, timeoutMs = 30000) {
  const t = localStorage.getItem('token');
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(API + path, {
      ...opts,
      signal: ctrl.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(t ? { Authorization: 'Bearer ' + t } : {}),
        ...(opts.headers || {}),
      },
    });
    if (!r.ok) {
      const text = await r.text().catch(() => '');
      throw new ApiError(r.status, HUMAN_BY_STATUS[r.status] || 'Не удалось выполнить действие. Попробуйте снова.', text);
    }
    return r.json();
  } finally {
    clearTimeout(timer);
  }
}

export const login = (email: string, password: string) =>
  api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
