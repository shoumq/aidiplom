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
