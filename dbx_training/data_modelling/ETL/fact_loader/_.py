from __future__ import annotations
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

def _lookup_date_sk(engine: Engine, dates: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"date": pd.to_datetime(dates, utc=True).dt.date.unique()})
    with engine.begin() as conn:
        tmp = "tmp_dates"
        df.to_sql(tmp, conn.connection, if_exists="replace", index=False)
        return pd.read_sql(f"""
            SELECT d.date, dd.date_sk
            FROM {tmp} d
            JOIN dw.dim_date dd ON dd.date = d.date
        """, conn.connection)

def _lookup_time_sk(engine: Engine, ts: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"time_hhmmss": pd.to_datetime(ts, utc=True).dt.time.unique()})
    with engine.begin() as conn:
        tmp = "tmp_times"
        df.to_sql(tmp, conn.connection, if_exists="replace", index=False)
        return pd.read_sql(f"""
            SELECT t.time_hhmmss, dt.time_sk
            FROM {tmp} t
            JOIN dw.dim_time dt ON dt.time_hhmmss = t.time_hhmmss
        """, conn.connection)

def load_fact_observation(engine: Engine, obs: pd.DataFrame, record_source: str) -> None:
    df = obs.copy()
    df["observed_ts"] = pd.to_datetime(df["observed_ts"], utc=True)

    date_map = _lookup_date_sk(engine, df["observed_ts"])
    time_map = _lookup_time_sk(engine, df["observed_ts"])

    df["date"] = df["observed_ts"].dt.date
    df["time_hhmmss"] = df["observed_ts"].dt.time

    df = df.merge(date_map, on="date", how="left").merge(time_map, on="time_hhmmss", how="left")

    with engine.begin() as conn:
        # current station + location SK
        st = pd.read_sql("""
            SELECT station_nk, station_sk, location_sk
            FROM dw.dim_station
            WHERE is_current = true
        """, conn.connection)

    df = df.merge(st, on="station_nk", how="left")
    df["record_source"] = record_source

    fact_cols = [
        "station_sk","location_sk","date_sk","time_sk","observed_ts",
        "temp_c","wind_mps","precip_mm","humidity_pct","pressure_hpa",
        "record_source"
    ]
    df_fact = df[fact_cols].dropna(subset=["station_sk","location_sk","date_sk","time_sk"])

    with engine.begin() as conn:
        df_fact.to_sql("fact_observation", conn.connection, schema="dw", if_exists="append", index=False)

def load_fact_forecast_accuracy(engine: Engine, fc: pd.DataFrame, record_source: str) -> None:
    df = fc.copy()
    df["run_ts"] = pd.to_datetime(df["run_ts"], utc=True)
    df["target_ts"] = pd.to_datetime(df["target_ts"], utc=True)

    date_map = _lookup_date_sk(engine, df["target_ts"])
    time_map = _lookup_time_sk(engine, df["target_ts"])

    df["date"] = df["target_ts"].dt.date
    df["time_hhmmss"] = df["target_ts"].dt.time
    df = df.merge(date_map, on="date", how="left").merge(time_map, on="time_hhmmss", how="left")

    with engine.begin() as conn:
        st = pd.read_sql("""
            SELECT station_nk, station_sk, location_sk
            FROM dw.dim_station
            WHERE is_current = true
        """, conn.connection)

        md = pd.read_sql("""
            SELECT model_nk, model_version, model_sk
            FROM dw.dim_weather_model
            WHERE is_current = true
        """, conn.connection)

    df = df.merge(st, on="station_nk", how="left").merge(md, on=["model_nk","model_version"], how="left")
    df["record_source"] = record_source

    fact_cols = [
        "model_sk","station_sk","location_sk","date_sk","time_sk",
        "run_ts","target_ts",
        "predicted_temp_c","actual_temp_c","abs_error_temp",
        "record_source"
    ]
    df_fact = df[fact_cols].dropna(subset=["model_sk","station_sk","location_sk","date_sk","time_sk"])

    with engine.begin() as conn:
        df_fact.to_sql("fact_forecast_accuracy", conn.connection, schema="dw", if_exists="append", index=False)
