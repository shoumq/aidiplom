import json
import hashlib
import hmac
import ipaddress
import logging
import math
import os
import re
import secrets
import socket
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import requests
from bs4 import BeautifulSoup
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from openai import BadRequestError, OpenAI, PermissionDeniedError
from pydantic import BaseModel, Field

BASE_URL = "https://api.aitunnel.ru/v1"
DEFAULT_MODEL = "claude-sonnet-5.5"
AITUNNEL_MODELS_URL = "https://api.aitunnel.ru/public/aitunnel/models/chat"
AITUNNEL_TIMEOUT = float(os.getenv("AITUNNEL_TIMEOUT", "900"))
AITUNNEL_MAX_RETRIES = int(os.getenv("AITUNNEL_MAX_RETRIES", "5"))
STORE = Path(os.getenv("CHATS_FILE", str(Path(__file__).with_name("chats.json"))))
AUTH_DB = Path(os.getenv("AUTH_DB", str(Path(__file__).with_name("auth.db"))))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
ALLOW_MOCK_PAY = os.getenv("ALLOW_MOCK_PAY", "1") == "1"
ALLOWED_ORIGINS = {value.strip() for value in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if value.strip()}
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "365"))
PRIVACY_VERSION = "2026-10-29"
LOCK = threading.RLock()
RATE_LOCK = threading.Lock()
RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
logger = logging.getLogger("writer.security")
MODEL_CACHE: dict[str, Any] = {"loaded_at": 0, "items": {}}

MODEL_OPTIONS = {
    "qwen3.7-flash": {"label": "Qwen 3.7 Flash", "tier": "Экономичная", "prompt_cost": 6, "completion_cost": 26},
    "gpt-5.6-luna": {"label": "GPT 5.6 Luna", "tier": "Быстрая", "prompt_cost": 40, "completion_cost": 240},
    "gemini-2.5-flash": {"label": "Gemini 2.5 Flash", "tier": "Сбалансированная", "prompt_cost": 60, "completion_cost": 500},
    "glm-5": {"label": "GLM 5", "tier": "Сильная", "prompt_cost": 200, "completion_cost": 640},
    "claude-sonnet-5.5": {"label": "Claude Sonnet 5.5", "tier": "Рекомендуем", "prompt_cost": 400, "completion_cost": 2000},
    "gpt-5.6-terra": {"label": "GPT 5.6 Terra", "tier": "Продвинутая", "prompt_cost": 400, "completion_cost": 2400},
    "claude-sonnet-4.6": {"label": "Claude Sonnet 4.6", "tier": "Продвинутая", "prompt_cost": 600, "completion_cost": 3000},
    "gpt-5.6-sol": {"label": "GPT 5.6 Sol", "tier": "Максимальная", "prompt_cost": 800, "completion_cost": 4000},
}

FORMAT_RULES = {
    "Эссе": "Чёткий тезис, развёрнутая аргументация, логичный вывод. Только связный текст, без маркированных и нумерованных списков. Мысли связывай переходами внутри абзацев.",
    "Реферат": "Классическая структура: введение, 2-4 главы с подзаголовками, заключение, список литературы. Глубокий, но живой аналитический стиль.",
    "Сообщение": "Коротко и по делу. Естественный полуформальный или дружеский тон. Без вводных вежливых фраз ни о чём, сразу к сути.",
    "Курсовая работа": (
        "Курсовая работа: самостоятельная учебная научно-практическая работа студента по дисциплине "
        "(обычно 25–35 страниц). Её цель: показать умение работать с литературой и данными, "
        "анализировать и делать обоснованные выводы. Типовая структура: введение (актуальность, цель, "
        "задачи, объект, предмет, методы), глава 1 — теоретическая (понятия, подходы, обзор литературы), "
        "глава 2 — аналитическая/практическая (анализ данных, расчёты, кейс), заключение (выводы по каждой "
        "задаче, подтверждение достижения цели), список литературы, приложения. Стиль: строгий научный, "
        "чёткие определения, безличные обороты где уместно; каждый параграф завершается коротким выводом; "
        "текст логически связан с целью и задачами из введения. Основной текст сплошной, без списков "
        "(перечисление задач во введении допустимо)."
    ),
    "Дипломная работа": (
        "Дипломная работа (выпускная квалификационная работа, ВКР): итоговая самостоятельная работа выпускника, "
        "подтверждающая готовность к профессиональной деятельности (обычно 60–80 страниц). Глубже курсовой: "
        "шире обзор литературы, обязательна самостоятельная аналитическая часть на данных объекта исследования "
        "и проектная глава с практическими рекомендациями и оценкой их эффекта. Типовая структура: введение "
        "(актуальность, степень разработанности, цель, задачи, объект, предмет, методы, практическая значимость), "
        "глава 1 — теоретические основы, глава 2 — анализ объекта, глава 3 — рекомендации/проект, заключение, "
        "список литературы, приложения. Стиль: строгий научный; выводы по каждой главе; прослеживается связь "
        "между задачами введения и главами; аргументы подкреплены данными и источниками. Основной текст сплошной, без списков."
    ),
}
TYPE_INFO = {
    "Эссе": "Короткий авторский текст с тезисом и аргументацией.",
    "Реферат": "Обзор темы по источникам: введение, главы, заключение.",
    "Сообщение": "Короткий текст для отправки, сразу к сути.",
    "Курсовая работа": "Учебная научно-практическая работа, ~25–35 стр.: введение, теория, анализ, заключение. Пишется по плану, раздел за разделом.",
    "Дипломная работа": "Выпускная работа (ВКР), ~60–80 стр.: теория, анализ объекта, проектная глава с рекомендациями. Пишется по плану, раздел за разделом.",
}
LONG_WORKS = {
    "Курсовая работа": {"words": 8000, "structure": "Введение (актуальность, цель, задачи, объект, предмет, методы); Глава 1 — теоретическая (2–3 параграфа); Глава 2 — аналитическая/практическая (2–3 параграфа); Заключение."},
    "Дипломная работа": {"words": 18000, "structure": "Введение (актуальность, цель, задачи, объект, предмет, методы, практическая значимость); Глава 1 — теоретические основы (3 параграфа); Глава 2 — анализ объекта исследования (3 параграфа); Глава 3 — рекомендации/проектная часть (2–3 параграфа); Заключение."},
}
LIVE_STYLE_DEFAULT = """ЖИВОЙ АВТОРСКИЙ ГОЛОС (научный стиль сохраняется, но текст не должен звучать как шаблон):
- Ломай ровный ритм: чередуй длинные сложные предложения (25–40 слов) с короткими (3–8 слов). Не ставь подряд три предложения одинаковой длины или конструкции.
- Абзацы разной длины: за абзацем из двух предложений может идти абзац из шести-семи. Не заканчивай каждый абзац обобщающей фразой: вывод ставь там, где он действительно нужен (конец параграфа).
- Не строй текст симметрично: избегай перечислений ровно из трёх пунктов, оборота «с одной стороны… с другой стороны» в каждом абзаце, одинаковых зачинов абзацев.
- Переходы между абзацами делай через содержание (уточнение, возражение, пример), а не через связки-штампы («кроме того», «следует отметить», «таким образом», «в рамках данного исследования»).
- Допускай авторскую позицию: осторожные оценки («на наш взгляд», «по данным …»), уточнения в скобках, редкие вводные вставки, короткое возражение самому себе с ответом.
- Конкретика вместо общих слов: названия показателей, периоды, примеры. Без пафоса и оценочных прилагательных.
- Не повторяй слова-маркеры: подбирай синонимы и меняй порядок слов (иногда начинай предложение с обстоятельства или дополнения).
- Язык остаётся грамотным: никаких специальных ошибок и опечаток."""
SUMMARY_MARK = "<<<РЕЗЮМЕ>>>"
SECTION_EXTRA = (
    "Ты пишешь ОДИН раздел большой работы, а не всю работу. НЕ добавляй раздел «Источники» "
    "и список литературы: он формируется отдельно (это правило важнее общих). "
    "Не придумывай цифры, названия компаний, статьи законов. "
)
RULES_TAIL = (
    "Правила ответа:\n"
    "- Только текст раздела: без заголовка, без нумерации, без подзаголовков.\n"
    "- Таблицы допустимы только в формате Markdown и только из данных пользователя.\n"
    "- Цифры, факты, статьи законов бери только из данных пользователя или найденных источников. "
    "Нет нужных данных: ставь пометку [ВСТАВИТЬ: что именно]. Не уверен в факте: [ПРОВЕРИТЬ].\n"
    f"- После текста с новой строки напиши {SUMMARY_MARK} и 2 предложения о том, что именно раскрыто в разделе."
)


class Settings(BaseModel):
    model: str = Field(DEFAULT_MODEL, min_length=1, max_length=100)
    work_type: str = Field("Эссе", min_length=1, max_length=50)
    language: str = Field("русский", min_length=1, max_length=30)
    words: int = Field(800, ge=50, le=6000)
    total_words: int = Field(8000, ge=3000, le=40000)
    style: str = Field("", max_length=3000)
    style_sample: str = Field("", max_length=10000)
    extra: str = Field("", max_length=5000)
    rewrite_level: int = 90
    use_search: bool = True
    links: list[str] = Field(default_factory=list, max_length=10)
    plan_mode: Literal["auto", "given"] = "auto"
    given_plan: str = Field("", max_length=20000)
    user_data: str = Field("", max_length=50000)
    live_style_enabled: bool = True
    live_style: str = LIVE_STYLE_DEFAULT


class ChatCreate(BaseModel):
    work_type: str = Field("Эссе", max_length=50)


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    settings: Settings
    order_id: str


class QuoteRequest(BaseModel):
    chat_id: str
    prompt: str = Field(min_length=1, max_length=20000)
    settings: Settings


class WriteRequest(BaseModel):
    settings: Settings


class ReviseRequest(BaseModel):
    section_index: int
    instruction: str = Field(min_length=1, max_length=10000)
    settings: Settings


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    privacy_accepted: bool = False


def _auth_connection():
    AUTH_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_DB)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _init_auth():
    with _auth_connection() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                chat_id TEXT NOT NULL,
                work_type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                settings_json TEXT NOT NULL,
                words INTEGER NOT NULL,
                pages INTEGER NOT NULL,
                amount_rub INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                paid_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS orders_user_id ON orders(user_id);
            CREATE INDEX IF NOT EXISTS orders_chat_id ON orders(chat_id);
            CREATE TABLE IF NOT EXISTS consents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                document TEXT NOT NULL,
                version TEXT NOT NULL,
                accepted_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS consents_user_id ON consents(user_id);
        """)


def _rate_limit(request: Request, scope: str, identity: str, limit: int, window: int):
    client = request.client.host if request.client else "unknown"
    key = f"{scope}:{client}:{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
    now = time.monotonic()
    with RATE_LOCK:
        bucket = RATE_BUCKETS[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429, "Слишком много запросов. Повторите попытку позже")
        bucket.append(now)


def _validate_settings(settings: Settings):
    if settings.work_type not in TYPE_INFO:
        raise HTTPException(422, "Неизвестный тип работы")
    if settings.model not in MODEL_OPTIONS:
        raise HTTPException(422, "Выбранная модель недоступна")
    if any(len(url) > 2048 for url in settings.links):
        raise HTTPException(422, "Ссылка слишком длинная")


def _normalise_email(email: str):
    value = email.strip().lower()
    if len(value) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise HTTPException(422, "Введите корректный email")
    return value


def _hash_password(password: str, salt=None):
    if len(password) < 8:
        raise HTTPException(422, "Пароль должен содержать не менее 8 символов")
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 310_000)
    return f"pbkdf2_sha256${salt_bytes.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str):
    try:
        _, salt, expected = encoded.split("$", 2)
        actual = _hash_password(password, salt).split("$", 2)[2]
        return hmac.compare_digest(actual, expected)
    except (ValueError, HTTPException):
        return False


def _token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def _create_session(user_id: str, response: Response):
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 30 * 24 * 60 * 60
    with _auth_connection() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        connection.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (_token_hash(token), user_id, expires_at))
    response.set_cookie("writer_session", token, max_age=30 * 24 * 60 * 60, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/")


def current_user(writer_session: str | None = Cookie(default=None)):
    if not writer_session:
        raise HTTPException(401, "Требуется авторизация")
    with _auth_connection() as connection:
        row = connection.execute(
            "SELECT users.id,users.email FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires_at>?",
            (_token_hash(writer_session), int(time.time())),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Сессия истекла. Войдите снова")
    return {"id": row["id"], "email": row["email"]}


_init_auth()


PRICE_RULES = {
    "Эссе": {"base": 29, "page": 15},
    "Реферат": {"base": 99, "page": 25},
    "Сообщение": {"base": 29, "page": 10},
    "Курсовая работа": {"base": 399, "page": 45},
    "Дипломная работа": {"base": 699, "page": 65},
}


def _model_catalog():
    now = time.time()
    if MODEL_CACHE["items"] and now - MODEL_CACHE["loaded_at"] < 15 * 60:
        return MODEL_CACHE["items"]
    items = {key: dict(value) for key, value in MODEL_OPTIONS.items()}
    try:
        response = requests.get(AITUNNEL_MODELS_URL, timeout=(3, 5), allow_redirects=False)
        response.raise_for_status()
        live = response.json()
        for model_id, item in items.items():
            source = live.get(model_id)
            if not source:
                continue
            item["prompt_cost"] = float(source.get("prompt_cost", item["prompt_cost"]))
            item["completion_cost"] = float(source.get("completion_cost", item["completion_cost"]))
            item["description"] = source.get("description", "")
            item["provider"] = source.get("provider", "")
        MODEL_CACHE.update({"loaded_at": now, "items": items})
    except Exception:
        logger.warning("Could not refresh AITunnel model catalog; using fallback prices", exc_info=True)
        if not MODEL_CACHE["items"]:
            MODEL_CACHE.update({"loaded_at": now, "items": items})
    return MODEL_CACHE["items"]


def _model_fee(settings: Settings, words: int):
    model = _model_catalog()[settings.model]
    # Russian academic prose averages roughly 1.8 output tokens per word. Input
    # reserve covers system prompts, plan, section summaries and source context.
    output_tokens = max(500, math.ceil(words * 1.8))
    input_tokens = max(2500, math.ceil(words * (0.75 if settings.work_type in LONG_WORKS else 0.4)))
    if settings.use_search:
        input_tokens += 1500
    raw_cost = input_tokens * model["prompt_cost"] / 1_000_000 + output_tokens * model["completion_cost"] / 1_000_000
    # Covers retries, plan generation and price fluctuation while the quote is locked.
    fee = max(1, math.ceil(raw_cost * 2.5))
    return fee, model


def _settings_json(settings: Settings):
    return json.dumps(settings.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _quote(settings: Settings):
    words = settings.total_words if settings.work_type in LONG_WORKS else settings.words
    words = max(1, words)
    pages = max(1, (words + 349) // 350)
    rule = PRICE_RULES.get(settings.work_type, PRICE_RULES["Эссе"])
    base = rule["base"]
    volume = pages * rule["page"]
    search = max(49, pages * 10) if settings.use_search else 0
    model_fee, model = _model_fee(settings, words)
    amount = max(49, base + volume + search + model_fee)
    return {
        "words": words,
        "pages": pages,
        "amount_rub": amount,
        "breakdown": [
            {"label": "Подготовка работы", "detail": f"Требования, логика и структура — {settings.work_type.lower()}", "amount_rub": base},
            {"label": "Написание основного текста", "detail": f"{pages} стр. × {rule['page']} ₽", "amount_rub": volume},
            {"label": f"ИИ-модель {model['label']}", "detail": "Расход AITunnel с резервом на контекст и повтор запроса", "amount_rub": model_fee},
            *([{"label": "Поиск и проверка источников", "detail": f"Поиск по теме и разделам: {pages} стр. × 10 ₽", "amount_rub": search}] if search else []),
        ],
        "includes": [
            "Текст выбранного объёма",
            *(["План и последовательная подготовка разделов"] if settings.work_type in LONG_WORKS else []),
            *(["Поиск источников и проверка ссылок"] if settings.use_search else []),
            "Готовый файл Word",
            "Сохранение результата и правки разделов",
        ],
    }


def _order_response(row, breakdown=None, includes=None):
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "work_type": row["work_type"],
        "words": row["words"],
        "pages": row["pages"],
        "amount_rub": row["amount_rub"],
        "status": row["status"],
        "expires_at": row["expires_at"],
        "breakdown": breakdown or [],
        "includes": includes or [],
        "payment_mode": "mock",
    }


def _paid_order(order_id: str, user_id: str, chat_id: str, prompt: str, settings: Settings):
    with _auth_connection() as connection:
        row = connection.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user_id)).fetchone()
    if not row or row["chat_id"] != chat_id:
        raise HTTPException(404, "Заказ не найден")
    if row["status"] not in ("paid", "generating"):
        raise HTTPException(402, "Сначала оплатите заказ")
    if row["prompt"] != prompt or row["settings_json"] != _settings_json(settings):
        raise HTTPException(409, "Параметры заказа изменились. Рассчитайте стоимость заново")
    return row


def _set_order_status(order_id: str, status: str):
    with _auth_connection() as connection:
        connection.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))


def _load() -> dict[str, Any]:
    if not STORE.exists():
        return {}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


CHATS = _load()


def _save():
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(CHATS, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_chat(user_id: str, work_type="Эссе"):
    cid = uuid.uuid4().hex[:8]
    CHATS[cid] = {"id": cid, "user_id": user_id, "title": "Новый чат", "work_type": work_type, "history": [], "fetched": {}, "lw": {}, "created_at": int(time.time()), "updated_at": int(time.time())}
    _save()
    return CHATS[cid]


def _chat(cid: str, user_id: str):
    if cid not in CHATS or CHATS[cid].get("user_id") != user_id:
        raise HTTPException(404, "Чат не найден")
    CHATS[cid]["updated_at"] = int(time.time())
    return CHATS[cid]


def _purge_expired_chats():
    cutoff = int(time.time()) - DATA_RETENTION_DAYS * 24 * 60 * 60
    expired = [key for key, chat in CHATS.items() if chat.get("updated_at", chat.get("created_at", int(time.time()))) < cutoff]
    for key in expired:
        del CHATS[key]
    if expired:
        _save()


def _safe_public_url(raw_url: str):
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(raw_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError
        return parsed.geturl()
    except (ValueError, OSError, UnicodeError) as exc:
        raise ValueError("Разрешены только публичные HTTPS-ссылки") from exc


def fetch_url(url: str, limit=12000):
    try:
        safe_url = _safe_public_url(url)
        result = requests.get(
            safe_url,
            timeout=(5, 15),
            headers={"User-Agent": "Avtorskaya/1.0"},
            allow_redirects=False,
            stream=True,
        )
        if 300 <= result.status_code < 400:
            raise ValueError("Перенаправления ссылок запрещены")
        result.raise_for_status()
        content_type = result.headers.get("content-type", "").lower()
        if not any(kind in content_type for kind in ("text/html", "text/plain", "application/xhtml+xml")):
            raise ValueError("Ссылка должна вести на текстовую страницу")
        chunks = []
        total = 0
        for chunk in result.iter_content(16384):
            total += len(chunk)
            if total > 2 * 1024 * 1024:
                raise ValueError("Страница слишком большая")
            chunks.append(chunk)
        encoding = result.encoding or "utf-8"
        page = b"".join(chunks).decode(encoding, errors="replace")
        soup = BeautifulSoup(page, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        return title, re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:limit]
    except Exception:
        logger.warning("Source fetch rejected or failed", exc_info=True)
        return None, "Не удалось безопасно загрузить источник"


def _client(settings: Settings):
    key = os.getenv("AITUNNEL_API_KEY", "")
    if not key:
        raise ValueError("AITUNNEL_API_KEY не задан на сервере")
    return OpenAI(
        api_key=key,
        base_url=BASE_URL,
        timeout=AITUNNEL_TIMEOUT,
        max_retries=AITUNNEL_MAX_RETRIES,
    )


def _error_detail(exc: Exception):
    name = type(exc).__name__
    message = str(exc).strip() or repr(exc)
    return f"{name}: {message}"


def run_model(settings: Settings, system: str, messages: list[dict], use_search=None):
    kwargs: dict[str, Any] = {"model": settings.model, "max_tokens": 8000, "messages": [{"role": "system", "content": system}, *messages]}
    if settings.use_search if use_search is None else use_search:
        kwargs["tools"] = [{"type": "aitunnel:web_search", "parameters": {"max_results": 5, "max_uses": 5}}]
    client = _client(settings)
    try:
        response = client.chat.completions.create(**kwargs)
    except (BadRequestError, PermissionDeniedError):
        if "tools" not in kwargs:
            raise
        kwargs.pop("tools")
        response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message
    cites = {}
    for annotation in getattr(message, "annotations", None) or []:
        citation = getattr(annotation, "url_citation", None)
        if citation and citation.url:
            cites[citation.url] = citation.title or citation.url
    return (message.content or "").strip(), cites


def build_system(s: Settings, words=None, section=False):
    source_type = "веб-поиск" if s.use_search else "свои знания"
    current_style = s.style or "ясный, аналитический, живой, без канцелярита"
    live_style = s.live_style if s.live_style_enabled else ""
    extra = (SECTION_EXTRA + (live_style or "") + "\n" if section else "") + (s.extra or "")
    system = f"""Ты — профессиональный автор текстов. Пишешь на языке: {s.language}.
Тип работы: {s.work_type}. Приблизительный объём: {words or s.words} слов.

ФОРМАТ:
{FORMAT_RULES[s.work_type]}

СТИЛЬ ({current_style}):
- Чередуй длину предложений: после длинной конструкции уместна короткая фраза.
- Избегай шаблонных оборотов и штампов («важно отметить», «таким образом», «в заключение», «несомненно», «стоит подчеркнуть»).
- Абзацы разной длины, конкретные факты и примеры вместо общих слов.
- Не повторяй одно и то же термин-сочетание в соседних абзацах, подбирай синонимы.

САМОСТОЯТЕЛЬНАЯ ПЕРЕРАБОТКА ИСТОЧНИКОВ (уровень: {s.rewrite_level}%):
- Не копируй формулировки источников. Пересказывай идеи своими словами, объединяй данные из разных источников, добавляй собственный анализ и примеры.
- Чем выше уровень, тем сильнее перестраивай структуру и синтаксис относительно источника.
- Прямые цитаты только короткие, в кавычках, с указанием источника.

ИСТОЧНИКИ:
- В первую очередь опирайся на материалы пользователя (теги <source>), затем на {source_type}.
- В конце ответа добавь раздел «Источники»: только то, что реально использовано. Ничего не выдумывай: если нет уверенности в факте или источнике, не используй его или сделай оговорку.

ПРАВКИ:
Если пользователь просит изменить уже написанный текст, внеси правки и верни полную обновлённую версию (если не просят только фрагмент).
"""
    if extra:
        system += f"\nДополнительные требования: {extra}\n"
    if s.style_sample:
        system += (
            "\nНапиши в манере автора следующего образца (длина фраз, лексика, тон), "
            "не копируя его содержание:\n"
            f"<style_sample>\n{s.style_sample}\n</style_sample>\n"
        )
    return system


def sources_block(chat, limit):
    blocks = [f'<source url="{u}" title="{v[0]}">\n{v[1][:limit]}\n</source>' for u, v in chat["fetched"].items() if v[0]]
    return "\n".join(blocks) or "—"


def clean_plan(raw):
    result = []
    for item in raw:
        title = str(item.get("title", "")).strip()
        if not title or title.lower().startswith("список"):
            continue
        result.append({"title": title, "level": 1 if int(item.get("level", 2)) == 1 else 2, "words": max(0, min(int(item.get("words", 0)), 1800)), "brief": str(item.get("brief", "")).strip()})
    if not any(x["words"] for x in result):
        raise ValueError("В плане нет разделов с объёмом")
    return result


def make_plan(chat, s: Settings, request: str):
    spec = LONG_WORKS[s.work_type]
    system = (
        f"Ты — научный руководитель. Составляешь план: {s.work_type}. Язык: {s.language}. "
        f"Общий объём основного текста ≈ {s.total_words} слов.\n"
        f"Типовая структура: {spec['structure']}\n\n"
        "Верни ТОЛЬКО JSON-массив, без пояснений и без markdown-ограждений. "
        'Элемент: {"title": str, "level": 1 или 2, "words": int, "brief": str}.\n'
        "- level 1: Введение, Заключение, заголовок главы («Глава 1. …»). level 2: параграфы («1.1. …»).\n"
        "- У заголовка главы words = 0 (своего текста нет, сразу идут параграфы).\n"
        "- У Введения, Заключения и параграфов words > 0, сумма words ≈ общему объёму, "
        "один раздел не больше 1500 слов.\n"
        "- brief: 1–2 предложения, что именно раскрыть (методы, показатели, данные).\n"
        "- Если в задании или в блоке «ГОТОВЫЙ ПЛАН» уже есть план, НЕ придумывай свой: сохрани его разделы, "
        "названия и порядок как есть, добавь только недостающие поля (level, words, brief). "
        "Если в готовом плане нет Введения или Заключения, добавь их.\n"
        "- Раздел «Список литературы» в план не включай."
    )
    current = chat["lw"].get("plan")
    if current:
        prompt = f"Текущий план:\n{json.dumps(current, ensure_ascii=False)}\n\nПравки пользователя:\n{request}\n\nВерни обновлённый план целиком."
    else:
        parts = [f"Тема и задание:\n{request}"]
        if s.plan_mode == "given" and s.given_plan.strip():
            parts.append(f"ГОТОВЫЙ ПЛАН (сохрани как есть):\n{s.given_plan.strip()}")
        parts.append(f"Материалы пользователя:\n{sources_block(chat, 1500)}")
        parts.append(f"Исходные данные пользователя:\n{s.user_data or '—'}")
        prompt = "\n\n".join(parts)
    text, _ = run_model(s, system, [{"role": "user", "content": prompt}], False)
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise ValueError("Модель не вернула JSON-план")
    return clean_plan(json.loads(match.group(0)))


def plan_markdown(plan):
    return "\n".join((f"\n**{x['title']}**" if x["level"] == 1 else f"- {x['title']}") + (f" (~{x['words']} слов)" if x["words"] else "") + (f": {x['brief']}" if x["brief"] else "") for x in plan)


def outline(plan):
    return "\n".join(("  " if x["level"] == 2 else "") + x["title"] for x in plan)


def gen_section(s, prompt, words):
    text, cites = run_model(s, build_system(s, words, True), [{"role": "user", "content": prompt}])
    body, _, summary = text.partition(SUMMARY_MARK)
    body = re.sub(r"^\s*#+ .*\n+", "", body.strip()).strip()
    return body, summary.strip() or body[:300], cites


def bibliography(chat, cites):
    sources = {u: v[0] for u, v in chat["fetched"].items() if v[0]}
    sources.update(cites)
    if not sources:
        return "[ВСТАВИТЬ: список литературы — нормативные акты, учебники, статьи]"
    today = date.today().strftime("%d.%m.%Y")
    return "\n\n".join(f"{n}. {title} [Электронный ресурс]. URL: {url} (дата обращения: {today})." for n, (url, title) in enumerate(sources.items(), 1))


def assemble(chat):
    lw = chat["lw"]
    written = lw.get("written", {})
    parts = []
    for index, section in enumerate(lw["plan"]):
        parts.append(("# " if section["level"] == 1 else "## ") + section["title"])
        if str(index) in written:
            parts.append(written[str(index)][0])
    parts += ["# Список литературы", bibliography(chat, lw.get("cites", {}))]
    return "\n\n".join(parts)


def md_to_docx(text):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(3), Cm(1.5), Cm(2), Cm(2)

    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Times New Roman", Pt(14)
    pf = normal.paragraph_format
    pf.line_spacing, pf.first_line_indent, pf.space_after = 1.5, Cm(1.25), Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for name, align in (("Heading 1", WD_ALIGN_PARAGRAPH.CENTER), ("Heading 2", WD_ALIGN_PARAGRAPH.LEFT)):
        heading = doc.styles[name]
        heading.font.name, heading.font.size, heading.font.bold = "Times New Roman", Pt(14), True
        heading.font.color.rgb = RGBColor(0, 0, 0)
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            heading.element.rPr.rFonts.attrib.pop(qn(attr), None)
        heading.paragraph_format.first_line_indent = Cm(0)
        heading.paragraph_format.alignment = align
        heading.paragraph_format.space_before = Pt(12)
        heading.paragraph_format.space_after = Pt(12)
    doc.styles["Heading 1"].paragraph_format.page_break_before = True

    def add_runs(paragraph, value):
        for chunk in re.split(r"(\*\*.+?\*\*|\*.+?\*)", value):
            if chunk.startswith("**") and chunk.endswith("**") and len(chunk) > 4:
                paragraph.add_run(chunk[2:-2]).bold = True
            elif chunk.startswith("*") and chunk.endswith("*") and len(chunk) > 2:
                paragraph.add_run(chunk[1:-1]).italic = True
            elif chunk:
                paragraph.add_run(chunk)

    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        index += 1
        if not line.strip():
            continue
        match = re.match(r"(#{1,6})\s+(.*)", line)
        if match:
            doc.add_heading(match.group(2).strip(), min(len(match.group(1)), 2))
        elif line.lstrip().startswith("|"):
            block = [line]
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                block.append(lines[index].rstrip())
                index += 1
            rows = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in block if not re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", row)]
            if rows:
                columns = max(len(row) for row in rows)
                table = doc.add_table(rows=len(rows), cols=columns)
                table.style = "Table Grid"
                for row_index, row in enumerate(rows):
                    for column_index in range(columns):
                        paragraph = table.cell(row_index, column_index).paragraphs[0]
                        run = paragraph.add_run(row[column_index] if column_index < len(row) else "")
                        run.font.size = Pt(12); run.bold = row_index == 0
                        paragraph.paragraph_format.first_line_indent = Cm(0)
                        paragraph.paragraph_format.line_spacing = 1.0
                        paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        elif line.lstrip().startswith(("- ", "• ")):
            add_runs(doc.add_paragraph(), "– " + line.lstrip()[2:])
        else:
            add_runs(doc.add_paragraph(), line.strip())

    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


app = FastAPI(title="Writer Agent API", version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
    if request.headers.get("content-length"):
        try:
            if int(request.headers["content-length"]) > 1_000_000:
                return JSONResponse({"detail": "Запрос слишком большой"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Некорректный запрос"}, status_code=400)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    response.headers["Cache-Control"] = "no-store"
    if COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/api/meta")
def meta():
    return {"work_types": TYPE_INFO, "long_works": LONG_WORKS, "models": _model_catalog(), "model_prices_unit": "₽ за 1 млн токенов", "languages": ["русский", "английский", "немецкий", "нидерландский"], "default_model": DEFAULT_MODEL, "live_style": LIVE_STYLE_DEFAULT, "privacy_version": PRIVACY_VERSION, "payment_mode": "mock" if ALLOW_MOCK_PAY else "external"}


@app.post("/api/auth/register", status_code=201)
def register(body: AuthRequest, response: Response, request: Request):
    email = _normalise_email(body.email)
    _rate_limit(request, "register", email, 5, 15 * 60)
    if not body.privacy_accepted:
        raise HTTPException(422, "Необходимо принять политику обработки персональных данных")
    password_hash = _hash_password(body.password)
    user_id = uuid.uuid4().hex
    try:
        with _auth_connection() as connection:
            connection.execute("INSERT INTO users(id,email,password_hash,created_at) VALUES(?,?,?,?)", (user_id, email, password_hash, int(time.time())))
            connection.execute(
                "INSERT INTO consents(id,user_id,document,version,accepted_at) VALUES(?,?,?,?,?)",
                (uuid.uuid4().hex, user_id, "privacy-policy", PRIVACY_VERSION, int(time.time())),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "Пользователь с таким email уже существует") from exc
    _create_session(user_id, response)
    return {"id": user_id, "email": email}


@app.post("/api/auth/login")
def login(body: AuthRequest, response: Response, request: Request):
    email = _normalise_email(body.email)
    _rate_limit(request, "login", email, 10, 15 * 60)
    with _auth_connection() as connection:
        row = connection.execute("SELECT id,email,password_hash FROM users WHERE email=?", (email,)).fetchone()
    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Неверный email или пароль")
    _create_session(row["id"], response)
    return {"id": row["id"], "email": row["email"]}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, writer_session: str | None = Cookie(default=None)):
    if writer_session:
        with _auth_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(writer_session),))
    response.delete_cookie("writer_session", path="/")


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return user


@app.get("/api/account/export")
def export_account(user=Depends(current_user)):
    with _auth_connection() as connection:
        consents = [dict(row) for row in connection.execute("SELECT document,version,accepted_at FROM consents WHERE user_id=?", (user["id"],))]
        orders = [dict(row) for row in connection.execute("SELECT id,chat_id,work_type,words,pages,amount_rub,status,created_at,paid_at FROM orders WHERE user_id=?", (user["id"],))]
    with LOCK:
        chats = [chat for chat in CHATS.values() if chat.get("user_id") == user["id"]]
    payload = json.dumps({"user": user, "consents": consents, "orders": orders, "chats": chats}, ensure_ascii=False, indent=2)
    return Response(payload, media_type="application/json; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="my-data.json"'})


@app.delete("/api/account", status_code=204)
def delete_account(response: Response, user=Depends(current_user)):
    with LOCK:
        for chat_id in [key for key, chat in CHATS.items() if chat.get("user_id") == user["id"]]:
            del CHATS[chat_id]
        _save()
    with _auth_connection() as connection:
        connection.execute("DELETE FROM orders WHERE user_id=?", (user["id"],))
        connection.execute("DELETE FROM consents WHERE user_id=?", (user["id"],))
        connection.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        connection.execute("DELETE FROM users WHERE id=?", (user["id"],))
    response.delete_cookie("writer_session", path="/")


@app.post("/api/orders/quote", status_code=201)
def create_quote(body: QuoteRequest, request: Request, user=Depends(current_user)):
    _rate_limit(request, "quote", user["id"], 30, 15 * 60)
    _validate_settings(body.settings)
    with LOCK:
        _chat(body.chat_id, user["id"])
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(422, "Укажите тему или задание")
    quote = _quote(body.settings)
    now = int(time.time())
    order_id = uuid.uuid4().hex
    with _auth_connection() as connection:
        connection.execute(
            """INSERT INTO orders(
                id,user_id,chat_id,work_type,prompt,settings_json,words,pages,
                amount_rub,status,created_at,expires_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order_id, user["id"], body.chat_id, body.settings.work_type,
                prompt, _settings_json(body.settings), quote["words"], quote["pages"],
                quote["amount_rub"], "awaiting_payment", now, now + 30 * 60,
            ),
        )
        row = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    return _order_response(row, quote["breakdown"], quote["includes"])


@app.post("/api/orders/{order_id}/mock-pay")
def mock_pay(order_id: str, user=Depends(current_user)):
    if not ALLOW_MOCK_PAY:
        raise HTTPException(404, "Способ оплаты недоступен")
    now = int(time.time())
    with _auth_connection() as connection:
        row = connection.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Заказ не найден")
        if row["status"] == "awaiting_payment" and row["expires_at"] < now:
            connection.execute("UPDATE orders SET status='expired' WHERE id=?", (order_id,))
            raise HTTPException(409, "Срок действия цены истёк. Рассчитайте стоимость заново")
        if row["status"] == "awaiting_payment":
            connection.execute("UPDATE orders SET status='paid',paid_at=? WHERE id=?", (now, order_id))
        row = connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    return _order_response(row)


@app.get("/api/chats")
def list_chats(user=Depends(current_user)):
    with LOCK:
        _purge_expired_chats()
        own_chats = [c for c in CHATS.values() if c.get("user_id") == user["id"]]
        if not own_chats:
            own_chats = [_new_chat(user["id"])]
        return [{"id": c["id"], "title": c["title"], "work_type": c["work_type"]} for c in reversed(own_chats)]


@app.post("/api/chats")
def create_chat(body: ChatCreate, user=Depends(current_user)):
    if body.work_type not in TYPE_INFO:
        raise HTTPException(422, "Неизвестный тип работы")
    with LOCK: return _new_chat(user["id"], body.work_type)


@app.get("/api/chats/{cid}")
def get_chat(cid: str, user=Depends(current_user)):
    with LOCK: return _chat(cid, user["id"])


@app.delete("/api/chats/{cid}", status_code=204)
def delete_chat(cid: str, user=Depends(current_user)):
    with LOCK:
        _chat(cid, user["id"]); del CHATS[cid]; _save()


@app.post("/api/chats/{cid}/messages")
def send_message(cid: str, body: PromptRequest, request: Request, user=Depends(current_user)):
    _rate_limit(request, "generate", user["id"], 12, 60 * 60)
    _validate_settings(body.settings)
    with LOCK:
        chat = _chat(cid, user["id"]); s = body.settings
        _paid_order(body.order_id, user["id"], cid, body.prompt.strip(), s)
        _set_order_status(body.order_id, "generating")
        chat["work_type"] = s.work_type
        new_urls = [url for url in s.links if url.startswith("http") and url not in chat["fetched"]]
        for url in new_urls:
            chat["fetched"][url] = list(fetch_url(url))
        api_text = body.prompt
        if new_urls:
            blocks = [f'<source url="{url}" title="{chat["fetched"][url][0] or url}">\n{chat["fetched"][url][1]}\n</source>' for url in new_urls]
            api_text = "Материалы от пользователя:\n" + "\n".join(blocks) + "\n\nЗадача:\n" + body.prompt
        chat["history"].append({"role": "user", "content": body.prompt, "api": api_text})
        if chat["title"] == "Новый чат": chat["title"] = body.prompt.replace("\n", " ")[:40]
        try:
            if s.work_type in LONG_WORKS:
                if chat["lw"].get("final"): raise ValueError("Работа уже написана. Используйте правку раздела или сбросьте план.")
                plan = make_plan(chat, s, body.prompt)
                chat["lw"].setdefault("topic", body.prompt)
                chat["lw"].update({"plan": plan, "written": {}, "cites": {}, "final": None, "order_id": body.order_id})
                total = sum(x["words"] for x in plan)
                answer = f"**План работы**\n\n{plan_markdown(plan)}\n\nСумма по плану: ~{total} слов. Правки плана пиши сюда же. Когда план устраивает, жми «Написать работу по плану» в сайдбаре."
            else:
                messages = [{"role": m["role"], "content": m["api"]} for m in chat["history"]]
                answer, cites = run_model(s, build_system(s), messages)
                if cites: answer += "\n\n---\n**Ссылки из веб-поиска:**\n" + "\n".join(f"- [{t}]({u})" for u, t in cites.items())
            chat["history"].append({"role": "assistant", "content": answer, "api": answer})
            if s.work_type not in LONG_WORKS:
                _set_order_status(body.order_id, "completed")
            _save(); return chat
        except Exception as exc:
            logger.exception("Generation failed for chat %s", cid)
            chat["history"].pop(); _save(); raise HTTPException(502, "Не удалось создать текст. Попробуйте ещё раз") from exc


@app.post("/api/chats/{cid}/write")
def write_work(cid: str, body: WriteRequest, request: Request, user=Depends(current_user)):
    _rate_limit(request, "long-generate", user["id"], 5, 60 * 60)
    _validate_settings(body.settings)
    with LOCK:
        chat = _chat(cid, user["id"]); lw = chat["lw"]
        if not lw.get("plan"): raise HTTPException(409, "Сначала составьте план")
        order_id = lw.get("order_id")
        if not order_id:
            raise HTTPException(402, "Для этой работы нет оплаченного заказа")
        with _auth_connection() as connection:
            order = connection.execute("SELECT status FROM orders WHERE id=? AND user_id=? AND chat_id=?", (order_id, user["id"], cid)).fetchone()
        if not order or order["status"] not in ("paid", "generating"):
            raise HTTPException(402, "Сначала оплатите заказ")
        written = lw.setdefault("written", {}); cites = lw.setdefault("cites", {})
        todo = [i for i, x in enumerate(lw["plan"]) if x["words"] > 0]
        try:
            for index in todo:
                if str(index) in written: continue
                section = lw["plan"][index]
                previous = [i for i in todo if i < index and str(i) in written]
                summaries = "\n".join(f"- {lw['plan'][i]['title']}: {written[str(i)][1]}" for i in previous) or "—"
                tail = written[str(previous[-1])][0][-1200:] if previous else "—"
                data = f"<data>\n{body.settings.user_data}\n</data>" if body.settings.user_data else "—"
                prompt = "\n\n".join([
                    f"Тема работы и задание: {lw['topic']}",
                    f"Общий план:\n{outline(lw['plan'])}",
                    f"Уже написано (кратко):\n{summaries}",
                    f"Конец предыдущего раздела (для плавного перехода, не повторяй):\n{tail}",
                    f"Исходные данные пользователя:\n{data}",
                    f"Материалы пользователя:\n{sources_block(chat, 3000)}",
                    f"ЗАДАЧА: напиши раздел «{section['title']}», объём не менее {section['words']} слов. Что раскрыть: {section['brief']}",
                    RULES_TAIL,
                ])
                text, summary, new_cites = gen_section(body.settings, prompt, section["words"])
                written[str(index)] = [text, summary]; cites.update(new_cites); _save()
            lw["final"] = assemble(chat)
            words = len(re.findall(r"\w+", lw["final"]))
            chat["history"].append({"role": "assistant", "content": lw["final"], "api": f"[Работа написана полностью (~{words} слов) и показана пользователю]"})
            _set_order_status(order_id, "completed")
            _save(); return chat
        except Exception as exc:
            logger.exception("Long work generation failed for chat %s", cid)
            _save(); raise HTTPException(502, "Ошибка на разделе; прогресс сохранён. Повторите попытку") from exc


@app.post("/api/chats/{cid}/revise")
def revise(cid: str, body: ReviseRequest, request: Request, user=Depends(current_user)):
    _rate_limit(request, "revise", user["id"], 10, 60 * 60)
    _validate_settings(body.settings)
    with LOCK:
        chat = _chat(cid, user["id"]); lw = chat["lw"]; key = str(body.section_index)
        if key not in lw.get("written", {}): raise HTTPException(409, "Раздел ещё не написан")
        section = lw["plan"][body.section_index]
        prompt = "\n\n".join([
            f"Тема работы и задание: {lw['topic']}",
            f"Общий план:\n{outline(lw['plan'])}",
            f"Исходные данные пользователя:\n{body.settings.user_data or '—'}",
            f"Текущий текст раздела «{section['title']}»:\n{lw['written'][key][0]}",
            f"Правка пользователя: {body.instruction}\n\nВерни полный обновлённый текст раздела.",
            RULES_TAIL,
        ])
        try:
            text, summary, cites = gen_section(body.settings, prompt, section["words"])
            lw["written"][key] = [text, summary]; lw["cites"].update(cites); lw["final"] = assemble(chat)
            for message in reversed(chat["history"]):
                if message["role"] == "assistant" and message["api"].startswith("[Работа написана"):
                    message["content"] = lw["final"]; break
            _save(); return chat
        except Exception as exc:
            logger.exception("Revision failed for chat %s", cid)
            raise HTTPException(502, "Не удалось переписать раздел. Повторите попытку") from exc


@app.delete("/api/chats/{cid}/work")
def reset_work(cid: str, user=Depends(current_user)):
    with LOCK: chat = _chat(cid, user["id"]); chat["lw"] = {}; _save(); return chat


@app.get("/api/chats/{cid}/download/{kind}")
def download(cid: str, kind: Literal["md", "docx"], user=Depends(current_user)):
    chat = _chat(cid, user["id"]); text = chat["lw"].get("final") or next((m["content"] for m in reversed(chat["history"]) if m["role"] == "assistant"), "")
    if not text: raise HTTPException(404, "Нет готового текста")
    if kind == "md": return Response(text, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="result.md"'})
    return Response(md_to_docx(text), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": 'attachment; filename="work.docx"'})
