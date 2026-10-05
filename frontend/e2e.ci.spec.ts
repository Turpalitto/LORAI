import { test, expect } from '@playwright/test';

// CI-стенд: backend на синтетических КР (scripts/seed_synthetic_data.py):
// SYNTH: Острый средний отит (H66.9), SYNTH: Хронический тонзиллит (J35.0).
const API = process.env.API_BASE ?? 'http://127.0.0.1:8000';

test('health: ok + 2 synth docs', async ({ request }) => {
  const r = await request.get(`${API}/health`);
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.ok).toBe(true);
  expect(j.documents).toBe(2);
});

test('chat: in-data (отит H66.9) отвечает', async ({ request }) => {
  const r = await request.post(`${API}/chat`, {
    data: { query: 'Острое воспаление среднего уха H66.9' },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.refused).toBe(false);
});

test('chat: вне домена — отказ', async ({ request }) => {
  const r = await request.post(`${API}/chat`, {
    data: { query: 'Как лечить инфаркт миокарда?' },
  });
  const j = await r.json();
  expect(j.refused).toBe(true);
});

test('search-protocol: H66.9 находит отит', async ({ request }) => {
  const r = await request.post(`${API}/search-protocol`, {
    data: { q: 'H66.9' },
  });
  const j = await r.json();
  expect((j.items ?? []).length).toBeGreaterThan(0);
});
