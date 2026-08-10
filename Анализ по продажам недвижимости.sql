/* Анализ рынка недвижимости ЛО и СПБ
 * Автор:Клепцов Алексей
 * Дата: 4 февраля 2026 года
*/

-- Задача 1: Время активности объявлений
-- Определим аномальные значения (выбросы) по значению перцентилей:
WITH limits AS (
    SELECT  
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY total_area) AS total_area_limit,
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY rooms) AS rooms_limit,
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY balcony) AS balcony_limit,
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY ceiling_height) AS ceiling_height_limit_h,
        PERCENTILE_DISC(0.01) WITHIN GROUP (ORDER BY ceiling_height) AS ceiling_height_limit_l
    FROM real_estate.flats     
),
-- Найдём id объявлений, которые не содержат выбросы, также оставим пропущенные данные:
filtered_id AS(
    SELECT id
    FROM real_estate.flats  
    WHERE 
        total_area < (SELECT total_area_limit FROM limits)
        AND (rooms < (SELECT rooms_limit FROM limits) OR rooms IS NULL)
        AND (balcony < (SELECT balcony_limit FROM limits) OR balcony IS NULL)
        AND ((ceiling_height < (SELECT ceiling_height_limit_h FROM limits)
            AND ceiling_height > (SELECT ceiling_height_limit_l FROM limits)) OR ceiling_height IS NULL)
    ),
    -- Основной набор данных с фильтрацией и категоризацией
ads_data AS (
    SELECT 
        a.id AS advertisement_id,
        a.first_day_exposition,
        a.days_exposition,
        a.last_price,
        f.total_area,
        f.rooms,
        f.balcony,
        f.ceiling_height,
        f.floor,
        f.floors_total,
        c.city,
        c.city_id,
        t.type AS locality_type,
        -- Стоимость квадратного метра
        CASE 
            WHEN f.total_area > 0 AND a.last_price > 0 
            THEN a.last_price / f.total_area 
            ELSE NULL 
        END AS price_per_sqm,
        -- Категория по времени активности
        CASE 
            WHEN a.days_exposition IS NULL OR a.days_exposition = 0 THEN 'non category'
            WHEN a.days_exposition BETWEEN 1 AND 30 THEN 'до месяца'
            WHEN a.days_exposition BETWEEN 31 AND 90 THEN 'до трех месяцев'
            WHEN a.days_exposition BETWEEN 91 AND 180 THEN 'до полугода'
            ELSE 'более полугода'
        END AS activity_segment,
        -- Регион (СПб или Лен.область) с учетом фильтации по городам 
        CASE 
           WHEN c.city = 'Санкт-Петербург' THEN 'Санкт-Петербург'
           WHEN t.type = 'город' THEN 'Ленинградская область' -- только города Лен.области
           ELSE 'Исключено' -- все остальные населенные пункты Лен.области
        END AS region
    FROM real_estate.advertisement a
    JOIN real_estate.flats f ON a.id = f.id
    JOIN real_estate.city c ON f.city_id = c.city_id
    JOIN real_estate.type t ON f.type_id = t.type_id
    WHERE 
        -- Только отфильтрованные ID (без выбросов)
        a.id IN (SELECT id FROM filtered_id)
        -- Только 2015-2018 годы включительно
        AND EXTRACT(YEAR FROM a.first_day_exposition) BETWEEN 2015 AND 2018        
),
-- Агрегированные данные
aggregated_data AS (
    SELECT 
        region,
        activity_segment,
        COUNT(*) AS ads_count,
        AVG(price_per_sqm)::numeric AS avg_price_sqm,
        AVG(total_area)::numeric AS avg_total_area,
        PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY rooms)::numeric AS median_rooms,
        PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY balcony)::numeric AS median_balcony,
        PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY floor)::numeric AS median_floor
    FROM ads_data
    WHERE region != 'Исключено' -- Исключаем негородские населенные пункты Лен.области
    GROUP BY region, activity_segment
),
-- Общее количество объявлений по регионам
total_by_region AS (
    SELECT 
        region,
        SUM(ads_count) AS total_ads
    FROM aggregated_data
    GROUP BY region
)
-- Основной анализ по категориям активности (только для проданных объявлений)
SELECT  
    ad.region AS "Регион",
    ad.activity_segment AS "Сегмент активности",
    ad.ads_count AS "Количество объявлений",
    ROUND(ad.ads_count * 100.0 / tr.total_ads, 2) AS "Доля в регионе, %",
    ROUND(ad.avg_price_sqm, 2) AS "Средняя стоимость кв. метра",
    ROUND(ad.avg_total_area, 2) AS "Средняя площадь",
    ad.median_rooms::integer AS "Медиана кол-ва комнат",
    ad.median_balcony::integer AS "Медиана кол-ва балконов",
    ad.median_floor::integer AS "Медиана этажности"
FROM aggregated_data ad
LEFT JOIN total_by_region tr ON ad.region = tr.region
WHERE ad.region IN ('Санкт-Петербург', 'Ленинградская область')
ORDER BY 
    CASE ad.region 
        WHEN 'Санкт-Петербург' THEN 1
        WHEN 'ЛенОбл' THEN 2
    END,
    CASE ad.activity_segment
        WHEN 'non category' THEN 0
        WHEN 'до месяца' THEN 1
        WHEN 'до трех месяцев' THEN 2
        WHEN 'до полугода' THEN 3
        WHEN 'более полугода' THEN 4
    END;
   

    -- Задача 2: Сезонность объявлений
    -- Определим аномальные значения (выбросы) по значению перцентилей:
    WITH limits AS (
    SELECT  
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY total_area) AS total_area_limit,
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY rooms) AS rooms_limit,
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY balcony) AS balcony_limit,
        PERCENTILE_DISC(0.99) WITHIN GROUP (ORDER BY ceiling_height) AS ceiling_height_limit_h,
        PERCENTILE_DISC(0.01) WITHIN GROUP (ORDER BY ceiling_height) AS ceiling_height_limit_l
    FROM real_estate.flats     
),
--Найдём id объявлений, которые не содержат выбросы, также оставим пропущенные данные:
filtered_id AS (
    SELECT id
    FROM real_estate.flats  
    WHERE 
        total_area < (SELECT total_area_limit FROM limits)
        AND (rooms < (SELECT rooms_limit FROM limits) OR rooms IS NULL)
        AND (balcony < (SELECT balcony_limit FROM limits) OR balcony IS NULL)
        AND ((ceiling_height < (SELECT ceiling_height_limit_h FROM limits)
            AND ceiling_height > (SELECT ceiling_height_limit_l FROM limits)) OR ceiling_height IS NULL)
),
-- Собираем информацию об объявлениях с датами публикации и продажи
ads_data AS (
    SELECT 
        a.id,
        a.first_day_exposition AS start_date,
        a.first_day_exposition + INTERVAL '1 day' * a.days_exposition AS end_date,
        a.days_exposition,
        a.last_price,
        f.total_area,
        c.city,
        tu.type AS locality_type,
-- Расчет стоимости квадратного метра
        CASE 
            WHEN f.total_area > 0 AND a.last_price > 0 
            THEN a.last_price / f.total_area 
            ELSE NULL 
        END AS price_per_sqm,
-- Определение региона
        CASE 
            WHEN c.city = 'Санкт-Петербург' THEN 'Санкт-Петербург'
            WHEN tu.type = 'город' THEN 'Ленинградская область'
            ELSE 'Исключено'
        END AS region
    FROM real_estate.advertisement a
    JOIN real_estate.flats f ON a.id = f.id
    JOIN real_estate.city c ON f.city_id = c.city_id
    JOIN real_estate.type tu ON f.type_id = tu.type_id
    WHERE 
        a.id IN (SELECT id FROM filtered_id)
        -- Только за период 2015-2018 годов
        AND EXTRACT(YEAR FROM a.first_day_exposition) BETWEEN 2015 AND 2018
        -- Только город
        AND tu.type = 'город'
),
-- Статистика по публикациям по месяцам
monthly_stats AS (
    SELECT 
        EXTRACT(MONTH FROM start_date) AS month_num,
        TO_CHAR(start_date, 'Month') AS month_name,
        COUNT(*) AS published_ads_count,
        AVG(price_per_sqm)::numeric(10,2) AS published_avg_price_sqm,
        AVG(total_area)::numeric(10,2) AS published_avg_total_area
    FROM ads_data
    WHERE region IN ('Санкт-Петербург', 'Ленинградская область')
    GROUP BY EXTRACT(MONTH FROM start_date), TO_CHAR(start_date, 'Month')
),
-- Статистика по продажам по месяцам
sold_stats AS (
    SELECT 
        EXTRACT(MONTH FROM end_date) AS month_num,
        COUNT(*) AS sold_ads_count,
        AVG(price_per_sqm)::numeric(10,2) AS sold_avg_price_sqm,
        AVG(total_area)::numeric(10,2) AS sold_avg_total_area
    FROM ads_data
    WHERE region IN ('Санкт-Петербург', 'Ленинградская область')
        AND end_date IS NOT NULL
    GROUP BY EXTRACT(MONTH FROM end_date)
)
-- Объединяем статистику публикаций и продаж по месяцам
SELECT 
    m.month_num AS "Месяц",
    TRIM(m.month_name) AS "Название месяца",
    m.published_ads_count AS "Количество опубликованных",
    COALESCE(s.sold_ads_count, 0) AS "Количество проданных",
    ROUND(m.published_avg_price_sqm, 2) AS "Средняя цена кв.м. при публикации, руб",
    ROUND(COALESCE(s.sold_avg_price_sqm, 0), 2) AS "Средняя цена кв.м. при продаже, руб",
    ROUND(m.published_avg_total_area, 2) AS "Средняя площадь при публикации, кв.м.",
    ROUND(COALESCE(s.sold_avg_total_area, 0), 2) AS "Средняя площадь при продаже, кв.м."
FROM monthly_stats m
LEFT JOIN sold_stats s ON m.month_num = s.month_num
ORDER BY m.month_num;