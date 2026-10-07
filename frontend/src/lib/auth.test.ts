import { describe, it, expect, beforeEach } from 'vitest';
import { decodeJwt, expiresInText, readSession } from './auth';
import { __resetStoreForTests, store } from './storage';

const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString('base64url');
const jwt = (payload: Record<string, unknown>) => `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(payload)}.sig`;

beforeEach(() => __resetStoreForTests());

describe('decodeJwt', () => {
  it('читает payload', () => {
    expect(decodeJwt(jwt({ sub: 'doctor@clinic.ru', role: 'doctor' }))).toMatchObject({
      sub: 'doctor@clinic.ru', role: 'doctor',
    });
  });

  it('возвращает null на мусоре', () => {
    expect(decodeJwt('не-токен')).toBeNull();
    expect(decodeJwt('a.b')).toBeNull();
    expect(decodeJwt('')).toBeNull();
  });
});

describe('readSession', () => {
  it('без токена сессии нет', () => {
    expect(readSession()).toBeNull();
  });

  it('восстанавливает роль и e-mail', () => {
    store.set('token', jwt({ sub: 'admin@lorai.local', role: 'admin', exp: 9999999999 }));
    const s = readSession(1_700_000_000);
    expect(s).toMatchObject({ email: 'admin@lorai.local', role: 'admin' });
  });

  it('просроченный токен удаляет', () => {
    store.set('token', jwt({ sub: 'x@y.z', role: 'doctor', exp: 1000 }));
    expect(readSession(5000)).toBeNull();
    expect(store.get('token')).toBeNull();
  });

  it('неизвестную роль считает врачом', () => {
    store.set('token', jwt({ sub: 'x@y.z', role: 'hacker', exp: 9999999999 }));
    expect(readSession(1)?.role).toBe('doctor');
  });
});

describe('expiresInText', () => {
  it('описывает остаток сессии по-русски', () => {
    const now = 1_000_000;
    expect(expiresInText(now + 600, now)).toMatch(/мин/);
    expect(expiresInText(now + 7200, now)).toMatch(/ч/);
    expect(expiresInText(now + 200000, now)).toMatch(/дн/);
    expect(expiresInText(now - 10, now)).toBe('сессия истекла');
    expect(expiresInText(null, now)).toBe('');
  });
});
