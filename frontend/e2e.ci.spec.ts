import { test, expect } from '@playwright/test';

// CI-стенд: backend на синтетических КР (scripts/seed_synthetic_data.py):
// SYNTH: Острый средний отит (H66.9), SYNTH: Хронический тонзиллит (J35.0).
const API = process.env.API_BASE ?? 'http://127.0.0.1:8000';

test('health: публичный ответ без счётчиков и режима LLM', async ({ request }) => {
  const r = await request.get(`${API}/health`);
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.ok).toBe(true);
  // С 1.4.0 публичный /health отдаёт только {ok, status, version}: число
  // документов/чанков и режим LLM раскрывали контур без авторизации.
  // Проверка стоит здесь как страж: если счётчики вернутся, тест упадёт.
  expect(j.documents).toBeUndefined();
  expect(j.chunks).toBeUndefined();
  expect(j.llm_mode).toBeUndefined();
  expect(typeof j.version).toBe('string');
});

test('admin/health: загружены 2 синтетических КР', async ({ request }) => {
  // Число документов доступно только админу — здесь и проверяем, что сид
  // реально попал в индекс (прежний тест ждал documents в публичном /health
  // и падал после ужесточения 1.4.0).
  const login = await request.post(`${API}/auth/login`, {
    data: {
      email: process.env.LORAI_ADMIN_EMAIL ?? 'admin@lorai.local',
      password: process.env.LORAI_ADMIN_PASSWORD ?? 'admin123',
    },
  });
  expect(login.ok()).toBeTruthy();
  const { token } = await login.json();
  const r = await request.get(`${API}/v1/admin/health`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.documents).toBe(2);
  expect(j.chunks).toBeGreaterThan(0);
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
