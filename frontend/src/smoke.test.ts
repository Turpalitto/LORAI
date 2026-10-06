import { describe, it, expect } from 'vitest';
import { DISC, API, APP_VERSION, ApiError, humanError } from './api/client';
describe('lorai smoke', () => {
  it('disclaimer present', () => { expect(DISC).toMatch(/Решение принимает врач/); });
  it('api url default', () => { expect(API).toMatch(/8000/); });
  it('human errors per status', () => {
    expect(humanError(new ApiError(401, 'Нужна авторизация.'))).toMatch(/авторизация/);
    expect(humanError(new TypeError('Failed to fetch'))).toMatch(/соединения/);
  });
  it('version pinned', () => { expect(APP_VERSION).toBe('1.1.0'); });
});
