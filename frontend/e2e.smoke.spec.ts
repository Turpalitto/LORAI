import { test, expect } from '@playwright/test';

const API = 'http://127.0.0.1:8000';

test('health: ok + 22 docs + disclaimer', async ({ request }) => {
  const r = await request.get(`${API}/health`);
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.ok).toBe(true);
  expect(j.documents).toBe(22);
  expect(j.disclaimer).toContain('врач');
});

test('chat: in-data отвечает с источниками', async ({ request }) => {
  const r = await request.post(`${API}/chat`, {
    data: { query: 'Какая доза амоксициллина ребенку при остром среднем отите?' },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.refused).toBe(false);
  expect((j.sources ?? []).length).toBeGreaterThan(0);
});

test('chat: вне домена — честный отказ', async ({ request }) => {
  const r = await request.post(`${API}/chat`, {
    data: { query: 'Как лечить инфаркт миокарда?' },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.refused).toBe(true);
});

test('search-protocol: находит по МКБ H66', async ({ request }) => {
  const r = await request.post(`${API}/search-protocol`, {
    data: { q: 'H66.0' },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  const items = j.items ?? j.results ?? j;
  expect(items.length).toBeGreaterThan(0);
});

test('diff-diagnosis: тризм → паратонзиллярный абсцесс первым', async ({ request }) => {
  const r = await request.post(`${API}/diff-diagnosis`, {
    data: { symptoms: ['тризм жевательных мышц', 'боль при глотании'] },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.ranked.length).toBeGreaterThan(0);
  expect(j.ranked[0].nosology).toContain('Паратонзиллярный');
});

test('dosage + calculators: считают', async ({ request }) => {
  const d = await request.post(`${API}/dosage`, {
    data: { weight_kg: 20, mg_per_kg: 45, max_mg: 1000, frequency: '2 раза в день' },
  });
  expect(d.ok()).toBeTruthy();
  const c = await request.post(`${API}/calculators/centor`, {
    data: { fever: true, exudate: true, nodes: true, cough: false, age: 25 },
  });
  expect(c.ok()).toBeTruthy();
  expect((await c.json()).score).toBe(3);
});

test('red-flags: стридор детектится', async ({ request }) => {
  const r = await request.post(`${API}/red-flags`, {
    data: { text: 'у ребенка стридор и одышка' },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  const flags = j.red_flags ?? j;
  expect(JSON.stringify(flags)).toContain('stridor');
});
