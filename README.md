# Writer Agent — FastAPI + Nuxt

## Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

API и Swagger: `http://localhost:8000/docs`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Интерфейс: `http://localhost:3000`.

Ключ AITunnel задаётся только на backend и не передаётся браузеру:

```bash
export AITUNNEL_API_KEY="sk-aitunnel-..."
```

## Docker Compose

```bash
cp .env.example .env
# впишите ключ AITunnel в .env
docker compose up --build
```

Frontend откроется на `http://localhost:3000`, API — на `http://localhost:8000`.
Чаты сохраняются в Docker volume `writer-data`.

### Публикация за reverse proxy

Для production направьте публичный `/` на frontend (`frontend:3000`), а `/api/` — на backend (`backend:8000`), сохраняя префикс `/api`. Тогда браузер обращается к API по тому же origin, а значение `NUXT_PUBLIC_API_BASE=/api` работает и на HTTP, и на HTTPS. В `.env` задайте точный публичный origin в `ALLOWED_ORIGINS` (например, `https://example.com`) и `COOKIE_SECURE=1`; включите HTTPS на proxy. Не публикуйте порт backend напрямую, если запросы идут через proxy.
