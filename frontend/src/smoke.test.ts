import { describe, it, expect } from 'vitest';
import { DISC, API } from './api/client';
describe('lorai smoke', () => {
  it('disclaimer present', () => { expect(DISC).toMatch(/Решение принимает врач/); });
  it('api url default', () => { expect(API).toMatch(/8000/); });
});
