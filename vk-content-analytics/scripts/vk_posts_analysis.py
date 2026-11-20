"""Анализ вовлечённости постов сообщества ВКонтакте.

Что делает:
1. Считает вовлечённость и два варианта ER: от подписчиков и от охвата
   (поле views). ER от охвата честнее: не зависит от размера сообщества.
2. Использует медианы вместо средних: вирусные посты тянут среднее вверх
   на порядок, медиана отражает типичный пост.
3. Разрезы: час публикации, день недели, длина текста, частота публикаций
   и интервал между постами.
4. Фото и видео/клипы считаются отдельно: у клипов поле views ведёт себя
   иначе (сотни репостов при нескольких тысячах просмотров), сравнивать
   их ER от охвата с фотопостами некорректно.
5. Сохраняет расширенный CSV (data/vk_posts_analysis.csv) — готовая база
   для дашборда (Yandex DataLens, Excel).

Вход: data/vk_posts.csv (создаётся vk_wall_export.py).
"""

import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
csv_path = BASE_DIR / "data" / "vk_posts.csv"

if not csv_path.exists():
    raise SystemExit("Файл data/vk_posts.csv не найден. Сначала запустите vk_wall_export.py.")

df = pd.read_csv(csv_path, parse_dates=["date_time"])
df["date"] = df["date_time"].dt.date

# --- 0. Проверка базы ---
assert df["subscribers"].nunique() == 1, "число подписчиков меняется между постами"
subs = df["subscribers"].iloc[0]

# --- 1. Вовлечённость и два варианта ER ---
df["engagement"] = df["likes"] + df["comments"] + df["shares"]
df["er_subscribers_pct"] = df["engagement"] / subs * 100
df["er_reach_pct"] = df["engagement"] / df["views"].clip(lower=1) * 100

# --- 2. Признаки времени ---
df["hour"] = df["date_time"].dt.hour
df["weekday"] = df["date_time"].dt.dayofweek  # 0 = понедельник

# интервал между постами (часы), в порядке публикации
df = df.sort_values("date_time").reset_index(drop=True)
df["gap_hours"] = df["date_time"].diff().dt.total_seconds() / 3600

# длина текста: корзины
bins = [-1, 100, 300, 700, 1500, 10**9]
labels = ["<=100", "101-300", "301-700", "701-1500", ">1500"]
df["text_bucket"] = pd.cut(df["text_length"], bins=bins, labels=labels)


def describe(group: pd.DataFrame) -> pd.Series:
    return pd.Series({
        "posts": len(group),
        "median_views": group["views"].median(),
        "median_engagement": group["engagement"].median(),
        "er_sub_median": group["er_subscribers_pct"].median(),
        "er_reach_median": group["er_reach_pct"].median(),
        "er_reach_mean": group["er_reach_pct"].mean(),
    })


def cut_video(df_all: pd.DataFrame):
    """Фото и видео считаем отдельно: у видео/клипов иная механика."""
    photos = df_all[df_all["content_type"] == "photo"]
    videos = df_all[df_all["content_type"].isin(["video", "clip"])]
    return photos, videos


# --- 3. Разрезы ---
for name, part in [("ФОТО", df[df.content_type == "photo"]),
                   ("ВИДЕО/КЛИПЫ", df[df.content_type.isin(["video", "clip"])])]:
    print(f"\n{'=' * 60}\n=== {name} ===\n{'=' * 60}")

    print("\n--- По часу публикации (медианы; для видео ER по подписчикам) ---")
    er_col = "er_reach_pct" if name == "ФОТО" else "er_subscribers_pct"
    table = part.groupby("hour").agg(
        posts=("engagement", "size"),
        median_views=("views", "median"),
        median_engagement=("engagement", "median"),
        median_er=(er_col, "median"),
    ).round(2)
    print(table.to_string())

    print("\n--- По дню недели ---")
    wd = part.groupby("weekday").agg(
        posts=("engagement", "size"),
        median_views=("views", "median"),
        median_engagement=("engagement", "median"),
        median_er=(er_col, "median"),
    ).round(2)
    print(wd.to_string())

    print("\n--- По длине текста ---")
    tb = part.groupby("text_bucket", observed=True).agg(
        posts=("engagement", "size"),
        median_views=("views", "median"),
        median_engagement=("engagement", "median"),
        median_er=(er_col, "median"),
    ).round(2)
    print(tb.to_string())

    print("\n--- Топ-10 постов по вовлечённости ---")
    top = part.nlargest(10, "engagement")[
        ["date_time", "text_length", "likes", "comments", "shares",
         "views", "er_subscribers_pct", "er_reach_pct"]
    ]
    top[top.select_dtypes(include="number").columns] = \
        top.select_dtypes(include="number").round(4)
    print(top.to_string(index=False))

# --- 4. Интервалы между постами ---
print(f"\n{'=' * 60}\n=== Частота публикаций ===")
print(f"Постов всего: {len(df)}")
print(f"Период: {df['date_time'].min():%Y-%m-%d} — {df['date_time'].max():%Y-%m-%d}")
print(f"Медианный интервал между постами: {df['gap_hours'].median():.2f} ч")
per_day = df.groupby("date").size()
print(f"Постов в день: медиана {per_day.median():.0f}, min {per_day.min()}, max {per_day.max()}")

print("\n--- Интервал по часам суток (когда чаще всего публикуют) ---")
print(df["hour"].value_counts().sort_index().to_string())

# --- 5. Сводка одним числом ---
print(f"\n{'=' * 60}")
print(f"Подписчиков: {subs:,}")
print(f"Средний ER от подписчиков по всем постам: "
      f"{df['er_subscribers_pct'].mean():.4f}% "
      f"(медиана {df['er_subscribers_pct'].median():.4f}%)")
photos, videos = cut_video(df)
if len(photos):
    p = photos[photos["views"] > 0]
    print(f"Фото: ER от охвата — медиана {p['er_reach_pct'].median():.2f}%, "
          f"среднее {p['er_reach_pct'].mean():.2f}%")
if len(videos):
    print(f"Видео: медианное соотношение (лайки+комменты+репосты)/просмотры "
          f"= {videos['er_reach_pct'].median():.0f}% — у клипов views ведёт "
          f"себя иначе, используйте ER от подписчиков")

# --- 6. Сохраняем расширенный CSV для дашборда ---
df["time_of_day"] = pd.cut(
    df["hour"], bins=[-1, 5, 11, 17, 22, 24],
    labels=["ночь 00-06", "утро 06-12", "день 12-18", "вечер 18-23", "поздний вечер 23+"],
)
out = BASE_DIR / "data" / "vk_posts_analysis.csv"
df.to_csv(out, index=False)
print(f"\nРасширенные данные сохранены: {out}")
