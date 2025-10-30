from datetime import datetime
from dataclasses import dataclass
from typing import Optional
from enum import Enum



class FileFormat(Enum):
    CSV = 'CSV'
    JSON = 'json'
    PARQUET = 'parquet'
    DELTA = 'delta'

class LoadType(Enum):
    FULL = 'full'
    INCREMENTAL = 'incremental'

class StorageType(Enum):
    ADLS = 'adls'
    S3 = 's3'
    GCS = 'gcs'

class metadataColumns(Enum):
    CREATED_DATE = 'created_date'
    UPDATED_DATE = 'updated_date'
    SOURCE_FILE = 'source_file'
    PROCESSING_TIMESTAMP = 'processing_timestamp'
    SOURCE_SYSTEM = 'source_system'


class ProcesTime:
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    @staticmethod
    def total_minutes(start_time: datetime, end_time: datetime) -> Optional[float]:
        if start_time and end_time:
            return self.duration_in_seconds/ 60
        return None
    
    @staticmethod
    def duration_in_seconds(start_time: datetime, end_time: datetime) -> Optional[float]:
        if start_time and end_time:
            duration = (end_time - start_time)
            return duration
        return None

