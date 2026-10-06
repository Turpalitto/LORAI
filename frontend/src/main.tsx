import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import App from './App';
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
createRoot(document.getElementById('root')!).render(<App />);
