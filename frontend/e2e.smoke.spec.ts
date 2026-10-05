import { test, expect } from '@playwright/test';
test('backend health', async ({ request }) => {
  const r = await request.get('http://localhost:8000/health');
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.ok).toBe(true);
});
