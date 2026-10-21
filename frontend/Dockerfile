# Сборка на Node из .nvmrc (24) и установка строго по lock-файлу.
# Было: node:20-alpine + `npm install` — версия Node расходилась с локальной
# (.nvmrc), а npm install мог подтянуть не те версии, что в package-lock.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Пустой VITE_API_URL = ходить на тот же origin (/v1), который проксирует
# nginx ниже. Иначе в бандл зашивался http://localhost:8000.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA-fallback и прокси /v1 → backend (см. nginx.conf).
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
