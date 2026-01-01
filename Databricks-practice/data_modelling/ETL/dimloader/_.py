from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from .dim_scd2 import scd2_upsert

def load_dim_date(engine: Engine, start_date: str, end_date: str) -> None:
    dts = pd.date_range(start=start_date, end=end_date, freq="D")
    df = pd.DataFrame({"date": dts.date})
    df["year"] = dts.year
    df["quarter"] = dts.quarter
    df["month"] = dts.month
    df["day"] = dts.day
    df["day_of_week"] = dts.dayofweek + 1
    df["is_weekend"] = df["day_of_week"].isin([6, 7])

    with engine.begin() as conn:
        # insert ignore duplicates
        tmp = "tmp_dim_date"
        df.to_sql(tmp, conn.connection, if_exists="replace", index=False)
        conn.execute(text(f"""
            INSERT INTO dw.dim_date(date, year, quarter, month, day, day_of_week, is_weekend)
            SELECT t.date, t.year, t.quarter, t.month, t.day, t.day_of_week, t.is_weekend
            FROM {tmp} t
            ON CONFLICT (date) DO NOTHING;
        """))

def load_dim_time(engine: Engine) -> None:
    times = pd.date_range("2000-01-01", "2000-01-01 23:59:59", freq="H")
    df = pd.DataFrame({"time_hhmmss": times.time})
    df["hour"] = times.hour
    df["minute"] = times.minute
    df["second"] = times.second

    with engine.begin() as conn:
        tmp = "tmp_dim_time"
        df.to_sql(tmp, conn.connection, if_exists="replace", index=False)
        conn.execute(text(f"""
            INSERT INTO dw.dim_time(time_hhmmss, hour, minute, second)
            SELECT t.time_hhmmss, t.hour, t.minute, t.second
            FROM {tmp} t
            ON CONFLICT (time_hhmmss) DO NOTHING;
        """))

def load_dim_location_scd2(engine: Engine, df_locations: pd.DataFrame, record_source: str, open_ended_to: str) -> None:
    df = df_locations.copy()
    df["effective_from_input"] = pd.Timestamp.utcnow()
    scd2_upsert(
        engine=engine,
        table="dw.dim_location",
        nk_cols=["location_nk"],
        attr_cols=["country","state_region","city","latitude","longitude","tz"],
        df_in=df,
        effective_from_col="effective_from_input",
        record_source=record_source,
        open_ended_to=open_ended_to,
    )

def load_dim_station_scd2(engine: Engine, df_stations: pd.DataFrame, record_source: str, open_ended_to: str) -> None:
    df = df_stations.copy()
    df["effective_from_input"] = pd.Timestamp.utcnow()
    scd2_upsert(
        engine=engine,
        table="dw.dim_station",
        nk_cols=["station_nk"],
        attr_cols=["station_name","station_type","elevation_m","status","location_nk"],
        df_in=df,
        effective_from_col="effective_from_input",
        record_source=record_source,
        open_ended_to=open_ended_to,
    )

def load_dim_model_scd2(engine: Engine, df_models: pd.DataFrame, record_source: str, open_ended_to: str) -> None:
    df = df_models.copy()
    df["effective_from_input"] = pd.Timestamp.utcnow()
    scd2_upsert(
        engine=engine,
        table="dw.dim_weather_model",
        nk_cols=["model_nk","model_version"],
        attr_cols=["vendor","resolution_km"],
        df_in=df,
        effective_from_col="effective_from_input",
        record_source=record_source,
        open_ended_to=open_ended_to,
    )

def resolve_station_location_sk(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE dw.dim_station s
               SET location_sk = l.location_sk
              FROM dw.dim_location l
             WHERE s.is_current = true
               AND l.is_current = true
               AND s.location_nk = l.location_nk
               AND (s.location_sk IS NULL OR s.location_sk <> l.location_sk);
        """))
