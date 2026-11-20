"""Выгрузка постов сообщества ВКонтакте в CSV для анализа вовлечённости.

Особенности:
- короткое имя сообщества резолвится через groups.getById: не нужно знать
  числовой id;
- owner_id ставится с минусом автоматически (частая причина ошибок wall.get);
- подписчики берутся живьём из members_count — ER считается от верной базы;
- сохраняется поле views (охват поста): с ним доступен ER и от охвата, и
  от подписчиков;
- признаки репоста и рекламы; сырые ответы API пишутся в JSON для проверки
  корректности данных;
- ретраи при rate limit (код 6) и пауза между запросами;
- offset сдвигается на фактическое число полученных постов: при удалённых
  постах фиксированный шаг перескакивал бы записи.

.env в корне папки проекта (не коммитится):
  VK_SERVICE_TOKEN=<сервисный токен>
  VK_GROUP_SCREEN=<короткое имя сообщества>
"""

import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

API_URL = "https://api.vk.com/method/"
TOKEN = os.getenv("VK_SERVICE_TOKEN")
SCREEN_NAME = os.getenv("VK_GROUP_SCREEN", "")
VERSION = "5.199"
COUNT_PER_REQUEST = 100
MAX_POSTS = 2000
PAUSE = 0.35  # ~3 запроса/сек, запас до лимита сервис-токена

DATA_DIR = BASE_DIR / "data"

if not TOKEN:
    raise SystemExit(
        "Не задан VK_SERVICE_TOKEN. Скопируйте .env.example в .env и вставьте "
        "сервисный токен приложения ВКонтакте."
    )
if not SCREEN_NAME:
    raise SystemExit("Не задан VK_GROUP_SCREEN (.env): короткое имя сообщества.")


def call(method: str, **params) -> dict:
    params.update({"access_token": TOKEN, "v": VERSION})
    for attempt in range(5):
        r = requests.get(API_URL + method, params=params, timeout=15)
        data = r.json()
        if "error" not in data:
            return data["response"]
        if data["error"].get("error_code") == 6:  # превышен лимит запросов
            time.sleep(1 + attempt)
            continue
        raise RuntimeError(f"{method}: {data['error'].get('error_msg')}")
    raise RuntimeError(f"{method}: не удалось выполнить запрос после ретраев")


def resolve_group(screen_name: str):
    resp = call("groups.getById", group_id=screen_name, fields="members_count")
    groups = resp.get("groups") or []
    if not groups:
        raise RuntimeError(f"Сообщество {screen_name} не найдено")
    g = groups[0]
    return -int(g["id"]), g


def fetch_all_posts(owner_id: int) -> list:
    posts, offset = [], 0
    while offset < MAX_POSTS:
        resp = call("wall.get", owner_id=owner_id,
                    count=COUNT_PER_REQUEST, offset=offset)
        items = resp.get("items", [])
        if not items:
            break
        posts.extend(items)
        offset += len(items)  # не COUNT_PER_REQUEST: выдача может содержать пропуски
        time.sleep(PAUSE)
    return posts


def content_type(post: dict) -> str:
    # приоритет: клип/видео важнее фото — пост с видео и картинкой это видео
    types = {a.get("type") for a in post.get("attachments", [])}
    for t in ("clip", "video", "photo", "audio", "poll", "link", "doc"):
        if t in types:
            return t
    return "text"


def save_raw(posts: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(posts, ensure_ascii=False), encoding="utf-8")


def save_to_csv(posts: list, filename: Path, subscribers: int) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date_time", "content_type", "text_length",
            "likes", "comments", "shares", "views",
            "is_repost", "is_ads", "subscribers",
        ])
        for p in posts:
            writer.writerow([
                datetime.fromtimestamp(p["date"]).strftime("%Y-%m-%d %H:%M"),
                content_type(p),
                len(p.get("text", "")),
                p.get("likes", {}).get("count", 0),
                p.get("comments", {}).get("count", 0),
                p.get("reposts", {}).get("count", 0),
                p.get("views", {}).get("count", 0),
                1 if p.get("copy_owner_id") else 0,
                p.get("marked_as_ads", 0),
                subscribers,
            ])


if __name__ == "__main__":
    owner_id, group = resolve_group(SCREEN_NAME)
    subscribers = group.get("members_count", 0)
    print(f"Сообщество: {group.get('name')} (id={group['id']}, "
          f"подписчиков={subscribers})")

    posts = fetch_all_posts(owner_id)
    print(f"Выгружено постов: {len(posts)}")

    if posts:
        oldest = datetime.fromtimestamp(min(p["date"] for p in posts))
        newest = datetime.fromtimestamp(max(p["date"] for p in posts))
        print(f"Период постов: {oldest:%Y-%m-%d} — {newest:%Y-%m-%d}")

    save_raw(posts, DATA_DIR / "vk_posts_raw.json")
    save_to_csv(posts, DATA_DIR / "vk_posts.csv", subscribers)
    print("Готово: data/vk_posts.csv")
