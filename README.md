# Writer Agent — FastAPI + Nuxt

## Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Backend: `http://localhost:8000`.

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

Frontend откроется на `http://localhost`. Браузер обращается к API через `/api` на том же адресе.
Чаты сохраняются в Docker volume `writer-data`.

### Публикация за reverse proxy

Для production направьте публичный `/` на frontend (`frontend:3000`), а `/api/` — на backend (`backend:8000`), сохраняя префикс `/api`. Тогда браузер обращается к API по тому же origin, а значение `NUXT_PUBLIC_API_BASE=/api` работает и на HTTP, и на HTTPS. В `.env` задайте точный публичный origin в `ALLOWED_ORIGINS` (например, `https://example.com`) и `COOKIE_SECURE=1`; включите HTTPS на proxy. Не публикуйте порт backend напрямую, если запросы идут через proxy.


### Документы и баланс

Поместите утверждённые тексты в `legal/privacy.txt` и `legal/offer.txt` (UTF-8).
Для запуска без Docker укажите путь к этой папке в `LEGAL_DIR`.
Версия документа вычисляется из его текста. Регистрация сохраняет принятую версию политики и оферты, оплата сохраняет принятую версию оферты.

Начислить внутренний баланс существующему аккаунту может оператор с доступом к серверу:

```bash
docker compose exec backend python -m backend.grant_credit user@example.com 500 grant-001
```

Используйте уникальный номер начисления. Повтор команды с тем же номером, аккаунтом и суммой оставляет баланс прежним.
В тестовом режиме первое подтверждение заказа с имитацией списания начисляет пригласившему 150 ₽ тестового баланса. Тестовые начисления и заказы действуют в тестовом режиме.
Для боевой оплаты и реферальных начислений нужен платёжный провайдер с подтверждением платежей и обработкой возвратов. При отключённой тестовой оплате заказ можно целиком покрыть внутренним балансом.

### Оплата через ЮKassa

В `.env` задайте `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и `PAYMENT_RETURN_URL=https://diplora.ru/`.
Укажите публичный HTTPS origin в `ALLOWED_ORIGINS`, включите `COOKIE_SECURE=1` и отключите имитацию через `ALLOW_MOCK_PAY=0`.
Для проверки используйте идентификатор и ключ тестового магазина. Настроенная ЮKassa имеет приоритет над имитацией.

В кабинете ЮKassa добавьте URL уведомлений `https://diplora.ru/api/payments/yookassa/webhook`
для событий `payment.succeeded` и `payment.canceled`. Сервер проверяет статус, сумму и номер заказа через API магазина.
Возврат на сайт открывает заказ и позволяет проверить оплату, затем продолжить генерацию.

Реквизиты карт вводятся на странице ЮKassa. Настройку выдачи чеков для самозанятого выполните в кабинете магазина.
API-запрос не содержит данных для онлайн-кассы. Автоматические возвраты в этой версии не реализованы.
При возврате через кабинет оператора требуется отдельно урегулировать использованный баланс и реферальное начисление.
