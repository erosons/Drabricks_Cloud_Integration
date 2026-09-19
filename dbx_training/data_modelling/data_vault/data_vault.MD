# Complete Data Vault 2.0 ETL Implementation

## Business Scenario: Retail Sales Data Vault

Building a scalable, auditable, and flexible enterprise data warehouse using Data Vault 2.0 methodology for retail operations.

---

## 1. DATA VAULT CONCEPTS

### What is Data Vault?

Data Vault is a detail-oriented, historical tracking, and uniquely linked set of normalized tables designed to support:
- **Auditability**: Complete audit trail of all data
- **Flexibility**: Easy to add new data sources
- **Scalability**: Parallel loading capabilities
- **Historization**: Track all changes over time

### Core Components

1. **HUBS**: Store unique business keys
   - Customer Hub, Product Hub, Store Hub, etc.
   - Contains only business key + metadata

2. **LINKS**: Store relationships between business keys
   - Sales Link (Customer-Product-Store relationship)
   - Many-to-many relationships

3. **SATELLITES**: Store descriptive attributes
   - Customer Satellite (name, address, etc.)
   - Product Satellite (description, price, etc.)
   - Track changes over time with load dates

### Data Vault 2.0 Features
- **Hash Keys**: MD5/SHA1 for performance
- **Hash Diffs**: Detect changes efficiently
- **Parallel Loading**: Load hubs, links, satellites independently
- **Point-in-Time (PIT) Tables**: Query optimization
- **Bridge Tables**: Multi-active satellites

---

## 2. CONCEPTUAL DESIGN

### Architecture Overview

```
Source Systems → Staging → Raw Vault → Business Vault → Information Marts
     (OLTP)       (ETL)    (Hubs/Links/Sats)  (PIT/Bridge)    (Dimensional)
```

### Entity Identification

**Business Keys:**
- Customer ID
- Product ID
- Store ID
- Transaction ID
- Promotion ID

**Relationships:**
- Customer purchases Products at Stores (Sales Link)
- Products associated with Promotions (Product-Promotion Link)

**Attributes:**
- Customer: demographics, contact info, segment
- Product: name, category, pricing
- Store: location, type, manager
- Transaction: amounts, quantities, dates

---

## 3. LOGICAL DESIGN

### Data Vault Model Structure

#### HUBS (5)
1. **hub_customer** - Customer business keys
2. **hub_product** - Product business keys
3. **hub_store** - Store business keys
4. **hub_transaction** - Transaction business keys
5. **hub_promotion** - Promotion business keys

#### LINKS (2)
1. **link_sales** - Customer-Product-Store-Transaction-Promotion relationship
2. **link_product_promotion** - Product-Promotion relationship

#### SATELLITES (8)
1. **sat_customer_details** - Customer descriptive attributes
2. **sat_customer_contact** - Customer contact information
3. **sat_product_details** - Product descriptions
4. **sat_product_pricing** - Product pricing (changes tracked)
5. **sat_store_details** - Store information
6. **sat_transaction_details** - Transaction amounts
7. **sat_promotion_details** - Promotion information
8. **sat_sales_metrics** - Sales measurements

#### POINT-IN-TIME TABLES (2)
1. **pit_customer** - Customer state at any point in time
2. **pit_product** - Product state at any point in time

---

## 4. PHYSICAL IMPLEMENTATION

### SQL Schema (PostgreSQL/MySQL Compatible)

```sql
-- =====================================================
-- DATA VAULT 2.0 PHYSICAL IMPLEMENTATION
-- =====================================================

-- Drop existing tables (reverse dependency order)
DROP TABLE IF EXISTS sat_sales_metrics;
DROP TABLE IF EXISTS sat_transaction_details;
DROP TABLE IF EXISTS sat_promotion_details;
DROP TABLE IF EXISTS sat_store_details;
DROP TABLE IF EXISTS sat_product_pricing;
DROP TABLE IF EXISTS sat_product_details;
DROP TABLE IF EXISTS sat_customer_contact;
DROP TABLE IF EXISTS sat_customer_details;
DROP TABLE IF EXISTS link_product_promotion;
DROP TABLE IF EXISTS link_sales;
DROP TABLE IF EXISTS hub_promotion;
DROP TABLE IF EXISTS hub_transaction;
DROP TABLE IF EXISTS hub_store;
DROP TABLE IF EXISTS hub_product;
DROP TABLE IF EXISTS hub_customer;
DROP TABLE IF EXISTS pit_customer;
DROP TABLE IF EXISTS pit_product;

-- =====================================================
-- HUB TABLES
-- =====================================================

-- Hub: Customer
CREATE TABLE hub_customer (
    hub_customer_hk CHAR(32) PRIMARY KEY,  -- MD5 hash key
    customer_id VARCHAR(50) NOT NULL UNIQUE,  -- Business key
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    INDEX idx_customer_id (customer_id),
    INDEX idx_load_date (load_date)
) COMMENT='Hub table for Customer business keys';

-- Hub: Product
CREATE TABLE hub_product (
    hub_product_hk CHAR(32) PRIMARY KEY,
    product_id VARCHAR(50) NOT NULL UNIQUE,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    INDEX idx_product_id (product_id),
    INDEX idx_load_date (load_date)
) COMMENT='Hub table for Product business keys';

-- Hub: Store
CREATE TABLE hub_store (
    hub_store_hk CHAR(32) PRIMARY KEY,
    store_id VARCHAR(50) NOT NULL UNIQUE,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    INDEX idx_store_id (store_id),
    INDEX idx_load_date (load_date)
) COMMENT='Hub table for Store business keys';

-- Hub: Transaction
CREATE TABLE hub_transaction (
    hub_transaction_hk CHAR(32) PRIMARY KEY,
    transaction_id VARCHAR(50) NOT NULL UNIQUE,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    INDEX idx_transaction_id (transaction_id),
    INDEX idx_load_date (load_date)
) COMMENT='Hub table for Transaction business keys';

-- Hub: Promotion
CREATE TABLE hub_promotion (
    hub_promotion_hk CHAR(32) PRIMARY KEY,
    promotion_id VARCHAR(50) NOT NULL UNIQUE,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    INDEX idx_promotion_id (promotion_id),
    INDEX idx_load_date (load_date)
) COMMENT='Hub table for Promotion business keys';

-- =====================================================
-- LINK TABLES
-- =====================================================

-- Link: Sales (Customer-Product-Store-Transaction-Promotion)
CREATE TABLE link_sales (
    link_sales_hk CHAR(32) PRIMARY KEY,  -- Hash of all hub keys
    hub_customer_hk CHAR(32) NOT NULL,
    hub_product_hk CHAR(32) NOT NULL,
    hub_store_hk CHAR(32) NOT NULL,
    hub_transaction_hk CHAR(32) NOT NULL,
    hub_promotion_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    
    FOREIGN KEY (hub_customer_hk) REFERENCES hub_customer(hub_customer_hk),
    FOREIGN KEY (hub_product_hk) REFERENCES hub_product(hub_product_hk),
    FOREIGN KEY (hub_store_hk) REFERENCES hub_store(hub_store_hk),
    FOREIGN KEY (hub_transaction_hk) REFERENCES hub_transaction(hub_transaction_hk),
    FOREIGN KEY (hub_promotion_hk) REFERENCES hub_promotion(hub_promotion_hk),
    
    INDEX idx_customer_hk (hub_customer_hk),
    INDEX idx_product_hk (hub_product_hk),
    INDEX idx_store_hk (hub_store_hk),
    INDEX idx_transaction_hk (hub_transaction_hk),
    INDEX idx_load_date (load_date)
) COMMENT='Link table for Sales transactions';

-- Link: Product-Promotion
CREATE TABLE link_product_promotion (
    link_product_promotion_hk CHAR(32) PRIMARY KEY,
    hub_product_hk CHAR(32) NOT NULL,
    hub_promotion_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100) NOT NULL,
    
    FOREIGN KEY (hub_product_hk) REFERENCES hub_product(hub_product_hk),
    FOREIGN KEY (hub_promotion_hk) REFERENCES hub_promotion(hub_promotion_hk),
    
    INDEX idx_product_hk (hub_product_hk),
    INDEX idx_promotion_hk (hub_promotion_hk),
    INDEX idx_load_date (load_date)
) COMMENT='Link table for Product-Promotion relationships';

-- =====================================================
-- SATELLITE TABLES
-- =====================================================

-- Satellite: Customer Details
CREATE TABLE sat_customer_details (
    hub_customer_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,  -- NULL = current record
    hash_diff CHAR(32) NOT NULL,  -- Hash of all attributes for change detection
    record_source VARCHAR(100) NOT NULL,
    
    -- Descriptive attributes
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    birth_date DATE,
    gender VARCHAR(10),
    customer_segment VARCHAR(50),
    registration_date DATE,
    
    PRIMARY KEY (hub_customer_hk, load_date),
    FOREIGN KEY (hub_customer_hk) REFERENCES hub_customer(hub_customer_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_load_end_date (load_end_date),
    INDEX idx_hash_diff (hash_diff)
) COMMENT='Satellite for Customer descriptive attributes';

-- Satellite: Customer Contact
CREATE TABLE sat_customer_contact (
    hub_customer_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Contact attributes
    email VARCHAR(255),
    phone VARCHAR(20),
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),
    
    PRIMARY KEY (hub_customer_hk, load_date),
    FOREIGN KEY (hub_customer_hk) REFERENCES hub_customer(hub_customer_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_load_end_date (load_end_date)
) COMMENT='Satellite for Customer contact information';

-- Satellite: Product Details
CREATE TABLE sat_product_details (
    hub_product_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Product attributes
    product_name VARCHAR(255),
    category VARCHAR(100),
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    supplier VARCHAR(255),
    
    PRIMARY KEY (hub_product_hk, load_date),
    FOREIGN KEY (hub_product_hk) REFERENCES hub_product(hub_product_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_load_end_date (load_end_date)
) COMMENT='Satellite for Product descriptive attributes';

-- Satellite: Product Pricing
CREATE TABLE sat_product_pricing (
    hub_product_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Pricing attributes
    unit_cost DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    currency VARCHAR(3) DEFAULT 'USD',
    
    PRIMARY KEY (hub_product_hk, load_date),
    FOREIGN KEY (hub_product_hk) REFERENCES hub_product(hub_product_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_load_end_date (load_end_date)
) COMMENT='Satellite for Product pricing (change tracked)';

-- Satellite: Store Details
CREATE TABLE sat_store_details (
    hub_store_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Store attributes
    store_name VARCHAR(255),
    store_type VARCHAR(50),
    manager VARCHAR(100),
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),
    phone VARCHAR(20),
    open_date DATE,
    square_footage INT,
    number_of_employees INT,
    
    PRIMARY KEY (hub_store_hk, load_date),
    FOREIGN KEY (hub_store_hk) REFERENCES hub_store(hub_store_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_load_end_date (load_end_date)
) COMMENT='Satellite for Store information';

-- Satellite: Transaction Details
CREATE TABLE sat_transaction_details (
    hub_transaction_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Transaction attributes
    transaction_date DATE,
    transaction_time TIME,
    payment_method VARCHAR(50),
    
    PRIMARY KEY (hub_transaction_hk, load_date),
    FOREIGN KEY (hub_transaction_hk) REFERENCES hub_transaction(hub_transaction_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_transaction_date (transaction_date)
) COMMENT='Satellite for Transaction details';

-- Satellite: Promotion Details
CREATE TABLE sat_promotion_details (
    hub_promotion_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Promotion attributes
    promotion_name VARCHAR(255),
    promotion_type VARCHAR(50),
    discount_percentage DECIMAL(5,2),
    start_date DATE,
    end_date DATE,
    description TEXT,
    
    PRIMARY KEY (hub_promotion_hk, load_date),
    FOREIGN KEY (hub_promotion_hk) REFERENCES hub_promotion(hub_promotion_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_start_date (start_date),
    INDEX idx_end_date (end_date)
) COMMENT='Satellite for Promotion details';

-- Satellite: Sales Metrics (attached to Link)
CREATE TABLE sat_sales_metrics (
    link_sales_hk CHAR(32) NOT NULL,
    load_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    load_end_date TIMESTAMP NULL,
    hash_diff CHAR(32) NOT NULL,
    record_source VARCHAR(100) NOT NULL,
    
    -- Sales metrics
    line_item_number INT,
    quantity INT,
    unit_price DECIMAL(10,2),
    discount_amount DECIMAL(10,2),
    tax_amount DECIMAL(10,2),
    total_amount DECIMAL(10,2),
    cost DECIMAL(10,2),
    profit DECIMAL(10,2),
    
    PRIMARY KEY (link_sales_hk, load_date),
    FOREIGN KEY (link_sales_hk) REFERENCES link_sales(link_sales_hk),
    
    INDEX idx_load_date (load_date),
    INDEX idx_load_end_date (load_end_date)
) COMMENT='Satellite for Sales metrics';

-- =====================================================
-- POINT-IN-TIME TABLES (for query optimization)
-- =====================================================

-- PIT: Customer
CREATE TABLE pit_customer (
    hub_customer_hk CHAR(32) NOT NULL,
    snapshot_date DATE NOT NULL,
    sat_customer_details_load_date TIMESTAMP,
    sat_customer_contact_load_date TIMESTAMP,
    
    PRIMARY KEY (hub_customer_hk, snapshot_date),
    FOREIGN KEY (hub_customer_hk) REFERENCES hub_customer(hub_customer_hk),
    
    INDEX idx_snapshot_date (snapshot_date)
) COMMENT='Point-in-Time table for Customer state';

-- PIT: Product
CREATE TABLE pit_product (
    hub_product_hk CHAR(32) NOT NULL,
    snapshot_date DATE NOT NULL,
    sat_product_details_load_date TIMESTAMP,
    sat_product_pricing_load_date TIMESTAMP,
    
    PRIMARY KEY (hub_product_hk, snapshot_date),
    FOREIGN KEY (hub_product_hk) REFERENCES hub_product(hub_product_hk),
    
    INDEX idx_snapshot_date (snapshot_date)
) COMMENT='Point-in-Time table for Product state';

-- =====================================================
-- STAGING TABLES
-- =====================================================

CREATE TABLE stg_transactions (
    transaction_id VARCHAR(50),
    transaction_date DATE,
    transaction_time TIME,
    customer_id VARCHAR(50),
    product_id VARCHAR(50),
    store_id VARCHAR(50),
    promotion_id VARCHAR(50),
    quantity INT,
    unit_price DECIMAL(10,2),
    discount_amount DECIMAL(10,2),
    tax_amount DECIMAL(10,2),
    line_item_number INT,
    payment_method VARCHAR(50),
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    record_source VARCHAR(100),
    
    INDEX idx_transaction_id (transaction_id),
    INDEX idx_load_timestamp (load_timestamp)
) COMMENT='Staging table for source transactions';

-- =====================================================
-- METADATA TABLES
-- =====================================================

CREATE TABLE etl_batch_log (
    batch_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    batch_name VARCHAR(255),
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP NULL,
    status VARCHAR(50),
    records_processed INT,
    records_inserted INT,
    records_updated INT,
    error_message TEXT
) COMMENT='ETL batch execution log';
```

---

## 5. PYTHON IMPLEMENTATION

### 5.1 Configuration Module

```python
# dv_config.py
"""
Data Vault ETL Configuration
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass
class DataVaultConfig:
    """Data Vault configuration"""
    # Database connection
    host: str = 'localhost'
    port: int = 3306
    database: str = 'retail_dv'
    username: str = 'dv_user'
    password: str = 'dv_password'
    
    # ETL settings
    batch_size: int = 1000
    hash_algorithm: str = 'md5'  # md5 or sha1
    record_source: str = 'RETAIL_OLTP'
    
    # Parallel loading
    enable_parallel: bool = True
    max_workers: int = 4
    
    # Change detection
    enable_hash_diff: bool = True
    track_deletes: bool = True
    
    def get_connection_string(self):
        return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

# Global configuration
dv_config = DataVaultConfig()
```

### 5.2 Hash Key Generation Module

```python
# dv_hash.py
"""
Hash key generation for Data Vault
"""
import hashlib
import pandas as pd
from typing import List, Union

class HashKeyGenerator:
    """Generate hash keys for Data Vault entities"""
    
    @staticmethod
    def generate_hash_key(values: Union[str, List[str]], algorithm='md5') -> str:
        """
        Generate hash key from business key(s)
        
        Args:
            values: Single value or list of values to hash
            algorithm: 'md5' or 'sha1'
        
        Returns:
            Hex hash string
        """
        if isinstance(values, list):
            # Concatenate multiple values with separator
            concat_value = '||'.join([str(v).upper().strip() for v in values])
        else:
            concat_value = str(values).upper().strip()
        
        if algorithm == 'md5':
            return hashlib.md5(concat_value.encode()).hexdigest()
        elif algorithm == 'sha1':
            return hashlib.sha1(concat_value.encode()).hexdigest()[:32]
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
    
    @staticmethod
    def generate_hash_diff(row: pd.Series, columns: List[str], algorithm='md5') -> str:
        """
        Generate hash diff for change detection in satellites
        
        Args:
            row: DataFrame row
            columns: List of column names to include in hash
            algorithm: 'md5' or 'sha1'
        
        Returns:
            Hex hash string
        """
        values = []
        for col in columns:
            val = row[col]
            if pd.isna(val):
                values.append('NULL')
            else:
                values.append(str(val).strip())
        
        concat_value = '||'.join(values)
        
        if algorithm == 'md5':
            return hashlib.md5(concat_value.encode()).hexdigest()
        else:
            return hashlib.sha1(concat_value.encode()).hexdigest()[:32]
    
    @staticmethod
    def add_hub_hash_key(df: pd.DataFrame, business_key_col: str, 
                        hub_name: str, algorithm='md5') -> pd.DataFrame:
        """Add hub hash key to DataFrame"""
        hash_col = f"hub_{hub_name}_hk"
        df[hash_col] = df[business_key_col].apply(
            lambda x: HashKeyGenerator.generate_hash_key(x, algorithm)
        )
        return df
    
    @staticmethod
    def add_link_hash_key(df: pd.DataFrame, hub_key_cols: List[str], 
                         link_name: str, algorithm='md5') -> pd.DataFrame:
        """Add link hash key to DataFrame"""
        hash_col = f"link_{link_name}_hk"
        df[hash_col] = df[hub_key_cols].apply(
            lambda row: HashKeyGenerator.generate_hash_key(row.tolist(), algorithm),
            axis=1
        )
        return df
    
    @staticmethod
    def add_hash_diff(df: pd.DataFrame, columns: List[str], 
                     algorithm='md5') -> pd.DataFrame:
        """Add hash diff column for change detection"""
        df['hash_diff'] = df[columns].apply(
            lambda row: HashKeyGenerator.generate_hash_diff(row, columns, algorithm),
            axis=1
        )
        return df

# Global instance
hash_gen = HashKeyGenerator()
```

### 5.3 Hub Loader Module

```python
# dv_hub_loader.py
"""
Hub table loading for Data Vault
"""
import pandas as pd
from datetime import datetime
import logging
from dv_hash import hash_gen
from dv_config import dv_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HubLoader:
    """Load Hub tables in Data Vault"""
    
    def __init__(self, db_manager, record_source=None):
        self.db = db_manager
        self.record_source = record_source or dv_config.record_source
    
    def load_hub(self, df: pd.DataFrame, hub_name: str, 
                 business_key_col: str) -> int:
        """
        Generic hub loading function
        
        Args:
            df: Source DataFrame
            hub_name: Name of the hub (e.g., 'customer', 'product')
            business_key_col: Column name containing business key
        
        Returns:
            Number of new records inserted
        """
        logger.info(f"Loading hub_{hub_name}...")
        
        # Generate hash key
        df_hub = df[[business_key_col]].drop_duplicates().copy()
        df_hub = hash_gen.add_hub_hash_key(
            df_hub, business_key_col, hub_name, dv_config.hash_algorithm
        )
        
        # Add metadata
        df_hub['load_date'] = datetime.now()
        df_hub['record_source'] = self.record_source
        
        # Get hash key column name
        hash_key_col = f"hub_{hub_name}_hk"
        
        # Check existing records
        existing_query = f"SELECT {hash_key_col} FROM hub_{hub_name}"
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
            existing_keys = set(df_existing[hash_key_col])
        except:
            existing_keys = set()
        
        # Filter to only new records
        df_new = df_hub[~df_hub[hash_key_col].isin(existing_keys)]
        
        if len(df_new) > 0:
            # Reorder columns for hub table
            columns = [hash_key_col, business_key_col, 'load_date', 'record_source']
            df_new = df_new[columns]
            
            # Insert new records
            self.db.bulk_insert(df_new, f'hub_{hub_name}', if_exists='append')
            logger.info(f"Built PIT table with {len(df_pit)} records")
        
        return len(pit_records)
    
    def build_pit_product(self, start_date=None, end_date=None):
        """
        Build PIT table for product
        """
        logger.info("Building pit_product...")
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).date()
        if end_date is None:
            end_date = datetime.now().date()
        
        df_products = pd.read_sql("SELECT hub_product_hk FROM hub_product", 
                                 self.db.engine)
        
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        pit_records = []
        
        for product_hk in df_products['hub_product_hk']:
            for snapshot_date in dates:
                query_details = f"""
                SELECT load_date 
                FROM sat_product_details
                WHERE hub_product_hk = '{product_hk}'
                AND load_date <= '{snapshot_date}'
                ORDER BY load_date DESC
                LIMIT 1
                """
                
                query_pricing = f"""
                SELECT load_date
                FROM sat_product_pricing
                WHERE hub_product_hk = '{product_hk}'
                AND load_date <= '{snapshot_date}'
                ORDER BY load_date DESC
                LIMIT 1
                """
                
                try:
                    details_load = pd.read_sql(query_details, self.db.engine)
                    pricing_load = pd.read_sql(query_pricing, self.db.engine)
                    
                    details_date = details_load.iloc[0]['load_date'] if len(details_load) > 0 else None
                    pricing_date = pricing_load.iloc[0]['load_date'] if len(pricing_load) > 0 else None
                    
                    if details_date or pricing_date:
                        pit_records.append({
                            'hub_product_hk': product_hk,
                            'snapshot_date': snapshot_date.date(),
                            'sat_product_details_load_date': details_date,
                            'sat_product_pricing_load_date': pricing_date
                        })
                except:
                    continue
        
        if pit_records:
            df_pit = pd.DataFrame(pit_records)
            self.db.truncate_table('pit_product')
            self.db.bulk_insert(df_pit, 'pit_product', if_exists='append')
            logger.info(f"Built PIT table with {len(df_pit)} records")
        
        return len(pit_records)
```

### 5.7 Main Data Vault ETL Orchestrator

```python
# dv_etl_pipeline.py
"""
Main Data Vault ETL Pipeline Orchestrator
"""
import pandas as pd
from datetime import datetime
import logging
from db_connection import db_manager
from dv_hub_loader import HubLoader
from dv_link_loader import LinkLoader
from dv_satellite_loader import SatelliteLoader
from dv_pit_builder import PITBuilder
from data_generator import DataGenerator
from dv_config import dv_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DataVaultETL:
    """Data Vault 2.0 ETL Pipeline Orchestrator"""
    
    def __init__(self):
        self.db = db_manager
        self.hub_loader = HubLoader(db_manager)
        self.link_loader = LinkLoader(db_manager)
        self.sat_loader = SatelliteLoader(db_manager)
        self.pit_builder = PITBuilder(db_manager)
        self.batch_id = None
    
    def initialize(self):
        """Initialize ETL pipeline"""
        logger.info("=" * 70)
        logger.info("DATA VAULT ETL PIPELINE INITIALIZATION")
        logger.info("=" * 70)
        
        self.db.connect()
        self.batch_id = int(datetime.now().strftime('%Y%m%d%H%M%S'))
        
        # Log batch start
        log_query = f"""
        INSERT INTO etl_batch_log (batch_name, status, start_time)
        VALUES ('DataVault_Full_Load', 'RUNNING', NOW())
        """
        self.db.execute_query(log_query)
        
        logger.info(f"Batch ID: {self.batch_id}")
        logger.info(f"Record Source: {dv_config.record_source}")
        logger.info(f"Hash Algorithm: {dv_config.hash_algorithm}")
    
    def extract_data(self, use_sample_data=True):
        """Extract data from source systems"""
        logger.info("=" * 70)
        logger.info("EXTRACT PHASE")
        logger.info("=" * 70)
        
        if use_sample_data:
            logger.info("Generating sample data...")
            generator = DataGenerator()
            
            data = {
                'customers': generator.generate_customers(1000),
                'products': generator.generate_products(500),
                'stores': generator.generate_stores(20),
                'promotions': generator.generate_promotions(50),
                'transactions': generator.generate_transactions(10000)
            }
        else:
            logger.info("Loading data from CSV files...")
            data = {
                'customers': pd.read_csv('data/customers.csv'),
                'products': pd.read_csv('data/products.csv'),
                'stores': pd.read_csv('data/stores.csv'),
                'promotions': pd.read_csv('data/promotions.csv'),
                'transactions': pd.read_csv('data/transactions.csv')
            }
        
        logger.info("Extract completed:")
        for key, df in data.items():
            logger.info(f"  - {key}: {len(df)} records")
        
        return data
    
    def transform_data(self, data):
        """Transform and prepare data for Data Vault"""
        logger.info("=" * 70)
        logger.info("TRANSFORM PHASE")
        logger.info("=" * 70)
        
        # Data quality checks
        logger.info("Running data quality checks...")
        
        # Remove duplicates
        for key in data:
            before = len(data[key])
            if key == 'transactions':
                data[key] = data[key].drop_duplicates(
                    subset=['transaction_id', 'line_item_number']
                )
            else:
                id_col = f"{key[:-1]}_id" if key != 'stores' else 'store_id'
                if id_col in data[key].columns:
                    data[key] = data[key].drop_duplicates(subset=[id_col])
            
            after = len(data[key])
            if before != after:
                logger.info(f"  Removed {before - after} duplicates from {key}")
        
        # Convert data types
        logger.info("Converting data types...")
        data['transactions']['transaction_date'] = pd.to_datetime(
            data['transactions']['transaction_date']
        )
        
        # Calculate derived fields for transactions
        logger.info("Calculating derived fields...")
        
        # Merge product costs for profit calculation
        product_costs = data['products'][['product_id', 'unit_cost']].copy()
        data['transactions'] = data['transactions'].merge(
            product_costs, on='product_id', how='left'
        )
        data['transactions']['cost'] = (
            data['transactions']['unit_cost'] * data['transactions']['quantity']
        )
        data['transactions']['total_amount'] = (
            data['transactions']['unit_price'] * data['transactions']['quantity'] -
            data['transactions']['discount_amount'] + 
            data['transactions']['tax_amount']
        )
        data['transactions']['profit'] = (
            data['transactions']['total_amount'] - data['transactions']['cost']
        )
        
        logger.info("Transform phase completed")
        return data
    
    def load_raw_vault(self, data):
        """Load Raw Vault (Hubs, Links, Satellites)"""
        logger.info("=" * 70)
        logger.info("LOAD RAW VAULT")
        logger.info("=" * 70)
        
        # Phase 1: Load Hubs (can be done in parallel)
        logger.info("\n--- PHASE 1: Loading Hubs ---")
        if dv_config.enable_parallel:
            hub_results = self.hub_loader.load_all_hubs_parallel(data)
        else:
            hub_results = {
                'customer': self.hub_loader.load_hub_customer(data['customers']),
                'product': self.hub_loader.load_hub_product(data['products']),
                'store': self.hub_loader.load_hub_store(data['stores']),
                'transaction': self.hub_loader.load_hub_transaction(data['transactions']),
                'promotion': self.hub_loader.load_hub_promotion(data['promotions'])
            }
        
        logger.info("Hub loading completed:")
        for hub, count in hub_results.items():
            logger.info(f"  hub_{hub}: {count} new records")
        
        # Phase 2: Load Links (requires hubs to be loaded)
        logger.info("\n--- PHASE 2: Loading Links ---")
        link_results = {
            'sales': self.link_loader.load_link_sales(data['transactions']),
            'product_promotion': self.link_loader.load_link_product_promotion(data['transactions'])
        }
        
        logger.info("Link loading completed:")
        for link, count in link_results.items():
            logger.info(f"  link_{link}: {count} new records")
        
        # Phase 3: Load Satellites (can be done in parallel)
        logger.info("\n--- PHASE 3: Loading Satellites ---")
        sat_results = {
            'customer_details': self.sat_loader.load_sat_customer_details(data['customers']),
            'customer_contact': self.sat_loader.load_sat_customer_contact(data['customers']),
            'product_details': self.sat_loader.load_sat_product_details(data['products']),
            'product_pricing': self.sat_loader.load_sat_product_pricing(data['products']),
            'store_details': self.sat_loader.load_sat_store_details(data['stores']),
            'transaction_details': self.sat_loader.load_sat_transaction_details(data['transactions']),
            'promotion_details': self.sat_loader.load_sat_promotion_details(data['promotions']),
            'sales_metrics': self.sat_loader.load_sat_sales_metrics(data['transactions'])
        }
        
        logger.info("Satellite loading completed:")
        for sat, count in sat_results.items():
            logger.info(f"  sat_{sat}: {count} records")
        
        return {
            'hubs': hub_results,
            'links': link_results,
            'satellites': sat_results
        }
    
    def build_business_vault(self):
        """Build Business Vault (PITs, Bridges)"""
        logger.info("=" * 70)
        logger.info("BUILD BUSINESS VAULT")
        logger.info("=" * 70)
        
        # Build Point-in-Time tables
        logger.info("Building PIT tables...")
        pit_results = {
            'customer': self.pit_builder.build_pit_customer(),
            'product': self.pit_builder.build_pit_product()
        }
        
        logger.info("PIT tables built:")
        for pit, count in pit_results.items():
            logger.info(f"  pit_{pit}: {count} records")
        
        return pit_results
    
    def generate_data_quality_report(self):
        """Generate comprehensive data quality report"""
        logger.info("=" * 70)
        logger.info("DATA QUALITY REPORT")
        logger.info("=" * 70)
        
        queries = {
            'Hub Counts': {
                'Customers': "SELECT COUNT(*) FROM hub_customer",
                'Products': "SELECT COUNT(*) FROM hub_product",
                'Stores': "SELECT COUNT(*) FROM hub_store",
                'Transactions': "SELECT COUNT(*) FROM hub_transaction",
                'Promotions': "SELECT COUNT(*) FROM hub_promotion"
            },
            'Link Counts': {
                'Sales': "SELECT COUNT(*) FROM link_sales",
                'Product-Promotion': "SELECT COUNT(*) FROM link_product_promotion"
            },
            'Current Satellite Records': {
                'Customer Details': "SELECT COUNT(*) FROM sat_customer_details WHERE load_end_date IS NULL",
                'Product Pricing': "SELECT COUNT(*) FROM sat_product_pricing WHERE load_end_date IS NULL",
                'Sales Metrics': "SELECT COUNT(*) FROM sat_sales_metrics WHERE load_end_date IS NULL"
            },
            'Historical Tracking': {
                'Customer Changes': """
                    SELECT COUNT(DISTINCT hub_customer_hk) as customers_with_changes
                    FROM sat_customer_details
                    WHERE load_end_date IS NOT NULL
                """,
                'Product Price Changes': """
                    SELECT COUNT(DISTINCT hub_product_hk) as products_with_price_changes
                    FROM sat_product_pricing
                    WHERE load_end_date IS NOT NULL
                """
            }
        }
        
        for section, section_queries in queries.items():
            logger.info(f"\n{section}:")
            for metric, query in section_queries.items():
                result = self.db.execute_query(query).fetchone()[0]
                logger.info(f"  {metric}: {result}")
    
    def update_batch_log(self, status, results=None):
        """Update ETL batch log"""
        records_processed = 0
        records_inserted = 0
        
        if results and 'hubs' in results:
            records_inserted += sum(results['hubs'].values())
        if results and 'links' in results:
            records_inserted += sum(results['links'].values())
        if results and 'satellites' in results:
            records_inserted += sum(results['satellites'].values())
        
        update_query = f"""
        UPDATE etl_batch_log
        SET status = '{status}',
            end_time = NOW(),
            records_inserted = {records_inserted}
        WHERE batch_id = (SELECT MAX(batch_id) FROM etl_batch_log)
        """
        self.db.execute_query(update_query)
    
    def run_full_load(self, use_sample_data=True, build_pit=True):
        """Execute complete Data Vault ETL pipeline"""
        try:
            start_time = datetime.now()
            logger.info("=" * 70)
            logger.info(f"DATA VAULT ETL STARTED AT {start_time}")
            logger.info("=" * 70)
            
            # Initialize
            self.initialize()
            
            # Extract
            data = self.extract_data(use_sample_data)
            
            # Transform
            data = self.transform_data(data)
            
            # Load Raw Vault
            results = self.load_raw_vault(data)
            
            # Build Business Vault
            if build_pit:
                pit_results = self.build_business_vault()
                results['pits'] = pit_results
            
            # Quality Report
            self.generate_data_quality_report()
            
            # Update batch log
            self.update_batch_log('SUCCESS', results)
            
            # Complete
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 70)
            logger.info("DATA VAULT ETL COMPLETED SUCCESSFULLY")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info("=" * 70)
            
            return results
            
        except Exception as e:
            logger.error(f"ETL Pipeline failed: {e}", exc_info=True)
            self.update_batch_log('FAILED')
            raise
        finally:
            self.db.close()
    
    def run_incremental_load(self, df_new_transactions):
        """Run incremental load for new transactions"""
        logger.info("=" * 70)
        logger.info("INCREMENTAL LOAD")
        logger.info("=" * 70)
        
        try:
            self.initialize()
            
            # Transform
            data = {'transactions': df_new_transactions}
            data = self.transform_data(data)
            
            # Load only affected structures
            results = {}
            
            # Load hubs
            hub_results = {
                'customer': self.hub_loader.load_hub_customer(data['transactions']),
                'product': self.hub_loader.load_hub_product(data['transactions']),
                'store': self.hub_loader.load_hub_store(data['transactions']),
                'transaction': self.hub_loader.load_hub_transaction(data['transactions']),
                'promotion': self.hub_loader.load_hub_promotion(data['transactions'])
            }
            results['hubs'] = hub_results
            
            # Load links
            link_results = {
                'sales': self.link_loader.load_link_sales(data['transactions'])
            }
            results['links'] = link_results
            
            # Load satellites
            sat_results = {
                'transaction_details': self.sat_loader.load_sat_transaction_details(data['transactions']),
                'sales_metrics': self.sat_loader.load_sat_sales_metrics(data['transactions'])
            }
            results['satellites'] = sat_results
            
            # Update batch log
            self.update_batch_log('SUCCESS', results)
            
            logger.info("Incremental load completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Incremental load failed: {e}")
            self.update_batch_log('FAILED')
            raise
        finally:
            self.db.close()

# Main execution
if __name__ == "__main__":
    pipeline = DataVaultETL()
    results = pipeline.run_full_load(use_sample_data=True, build_pit=True)
```

### 5.8 Data Vault Query Module

```python
# dv_queries.py
"""
Data Vault Query Examples and Analytics
"""
import pandas as pd
import logging
from db_connection import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataVaultAnalytics:
    """Query Data Vault for analytics"""
    
    def __init__(self):
        self.db = db_manager
        self.db.connect()
    
    def get_current_customer_view(self, customer_id=None):
        """
        Get current complete customer view (as-of-now)
        """
        where_clause = f"WHERE h.customer_id = '{customer_id}'" if customer_id else ""
        
        query = f"""
        SELECT 
            h.customer_id,
            sd.first_name,
            sd.last_name,
            sd.gender,
            sd.birth_date,
            sd.customer_segment,
            sc.email,
            sc.phone,
            sc.city,
            sc.state,
            sd.load_date as details_last_updated,
            sc.load_date as contact_last_updated
        FROM hub_customer h
        LEFT JOIN sat_customer_details sd 
            ON h.hub_customer_hk = sd.hub_customer_hk
            AND sd.load_end_date IS NULL
        LEFT JOIN sat_customer_contact sc
            ON h.hub_customer_hk = sc.hub_customer_hk
            AND sc.load_end_date IS NULL
        {where_clause}
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Retrieved {len(df)} current customer records")
        return df
    
    def get_customer_history(self, customer_id):
        """
        Get complete history of customer changes
        """
        query = f"""
        SELECT 
            'Details' as satellite_type,
            sd.load_date,
            sd.load_end_date,
            sd.customer_segment,
            NULL as email,
            NULL as phone
        FROM hub_customer h
        JOIN sat_customer_details sd ON h.hub_customer_hk = sd.hub_customer_hk
        WHERE h.customer_id = '{customer_id}'
        
        UNION ALL
        
        SELECT 
            'Contact' as satellite_type,
            sc.load_date,
            sc.load_end_date,
            NULL as customer_segment,
            sc.email,
            sc.phone
        FROM hub_customer h
        JOIN sat_customer_contact sc ON h.hub_customer_hk = sc.hub_customer_hk
        WHERE h.customer_id = '{customer_id}'
        
        ORDER BY load_date DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Retrieved {len(df)} historical records for customer {customer_id}")
        return df
    
    def get_product_price_history(self, product_id):
        """
        Track product price changes over time
        """
        query = f"""
        SELECT 
            h.product_id,
            pd.product_name,
            pd.category,
            pp.unit_cost,
            pp.unit_price,
            pp.load_date as effective_date,
            pp.load_end_date,
            CASE 
                WHEN pp.load_end_date IS NULL THEN 'Current'
                ELSE 'Historical'
            END as status
        FROM hub_product h
        JOIN sat_product_details pd 
            ON h.hub_product_hk = pd.hub_product_hk
            AND pd.load_end_date IS NULL
        JOIN sat_product_pricing pp
            ON h.hub_product_hk = pp.hub_product_hk
        WHERE h.product_id = '{product_id}'
        ORDER BY pp.load_date DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Retrieved {len(df)} price history records")
        return df
    
    def get_sales_with_context(self, limit=100):
        """
        Get sales transactions with full context (point-in-time accurate)
        """
        query = f"""
        SELECT 
            ht.transaction_id,
            std.transaction_date,
            hc.customer_id,
            scd.first_name,
            scd.last_name,
            hp.product_id,
            spd.product_name,
            spd.category,
            hs.store_id,
            ssd.store_name,
            ssd.city as store_city,
            ssm.quantity,
            ssm.unit_price,
            ssm.total_amount,
            ssm.profit
        FROM link_sales ls
        JOIN hub_transaction ht ON ls.hub_transaction_hk = ht.hub_transaction_hk
        JOIN hub_customer hc ON ls.hub_customer_hk = hc.hub_customer_hk
        JOIN hub_product hp ON ls.hub_product_hk = hp.hub_product_hk
        JOIN hub_store hs ON ls.hub_store_hk = hs.hub_store_hk
        LEFT JOIN sat_transaction_details std 
            ON ht.hub_transaction_hk = std.hub_transaction_hk
            AND std.load_end_date IS NULL
        LEFT JOIN sat_customer_details scd
            ON hc.hub_customer_hk = scd.hub_customer_hk
            AND scd.load_end_date IS NULL
        LEFT JOIN sat_product_details spd
            ON hp.hub_product_hk = spd.hub_product_hk
            AND spd.load_end_date IS NULL
        LEFT JOIN sat_store_details ssd
            ON hs.hub_store_hk = ssd.hub_store_hk
            AND ssd.load_end_date IS NULL
        LEFT JOIN sat_sales_metrics ssm
            ON ls.link_sales_hk = ssm.link_sales_hk
            AND ssm.load_end_date IS NULL
        ORDER BY std.transaction_date DESC
        LIMIT {limit}
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Retrieved {len(df)} sales records with context")
        return df
    
    def get_sales_as_of_date(self, as_of_date):
        """
        Get sales data as it appeared on a specific date (time travel query)
        Uses PIT tables for optimization
        """
        query = f"""
        SELECT 
            ht.transaction_id,
            std.transaction_date,
            hc.customer_id,
            scd.customer_segment,
            hp.product_id,
            spd.product_name,
            spp.unit_price as historical_price,
            ssm.quantity,
            ssm.total_amount
        FROM link_sales ls
        JOIN hub_transaction ht ON ls.hub_transaction_hk = ht.hub_transaction_hk
        JOIN hub_customer hc ON ls.hub_customer_hk = hc.hub_customer_hk
        JOIN hub_product hp ON ls.hub_product_hk = hp.hub_product_hk
        
        -- Use PIT tables for efficient point-in-time lookup
        JOIN pit_customer pc 
            ON hc.hub_customer_hk = pc.hub_customer_hk
            AND pc.snapshot_date = '{as_of_date}'
        JOIN sat_customer_details scd
            ON hc.hub_customer_hk = scd.hub_customer_hk
            AND scd.load_date = pc.sat_customer_details_load_date
        
        JOIN pit_product pp
            ON hp.hub_product_hk = pp.hub_product_hk
            AND pp.snapshot_date = '{as_of_date}'
        JOIN sat_product_details spd
            ON hp.hub_product_hk = spd.hub_product_hk
            AND spd.load_date = pp.sat_product_details_load_date
        JOIN sat_product_pricing spp
            ON hp.hub_product_hk = spp.hub_product_hk
            AND spp.load_date = pp.sat_product_pricing_load_date
        
        LEFT JOIN sat_transaction_details std
            ON ht.hub_transaction_hk = std.hub_transaction_hk
            AND std.load_end_date IS NULL
        LEFT JOIN sat_sales_metrics ssm
            ON ls.link_sales_hk = ssm.link_sales_hk
            AND ssm.load_end_date IS NULL
        
        WHERE std.transaction_date <= '{as_of_date}'
        ORDER BY std.transaction_date DESC
        LIMIT 100
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Retrieved {len(df)} sales records as of {as_of_date}")
        return df
    
    def sales_by_customer_segment(self):
        """Aggregate sales by customer segment"""
        query = """
        SELECT 
            scd.customer_segment,
            COUNT(DISTINCT hc.customer_id) as customer_count,
            COUNT(DISTINCT ht.transaction_id) as transaction_count,
            ROUND(SUM(ssm.total_amount), 2) as total_revenue,
            ROUND(SUM(ssm.profit), 2) as total_profit,
            ROUND(AVG(ssm.total_amount), 2) as avg_transaction_value
        FROM link_sales ls
        JOIN hub_customer hc ON ls.hub_customer_hk = hc.hub_customer_hk
        JOIN hub_transaction ht ON ls.hub_transaction_hk = ht.hub_transaction_hk
        JOIN sat_customer_details scd 
            ON hc.hub_customer_hk = scd.hub_customer_hk
            AND scd.load_end_date IS NULL
        JOIN sat_sales_metrics ssm
            ON ls.link_sales_hk = ssm.link_sales_hk
            AND ssm.load_end_date IS NULL
        GROUP BY scd.customer_segment
        ORDER BY total_revenue DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Sales by customer segment:")
        print(df.to_string(index=False))
        return df
    
    def top_products_by_category(self, limit=10):
        """Top selling products by category"""
        query = f"""
        SELECT 
            spd.category,
            spd.product_name,
            spd.brand,
            SUM(ssm.quantity) as units_sold,
            ROUND(SUM(ssm.total_amount), 2) as revenue,
            ROUND(SUM(ssm.profit), 2) as profit
        FROM link_sales ls
        JOIN hub_product hp ON ls.hub_product_hk = hp.hub_product_hk
        JOIN sat_product_details spd
            ON hp.hub_product_hk = spd.hub_product_hk
            AND spd.load_end_date IS NULL
        JOIN sat_sales_metrics ssm
            ON ls.link_sales_hk = ssm.link_sales_hk
            AND ssm.load_end_date IS NULL
        GROUP BY spd.category, spd.product_name, spd.brand
        ORDER BY revenue DESC
        LIMIT {limit}
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Top {limit} products:")
        print(df.to_string(index=False))
        return df
    
    def run_all_analytics(self):
        """Execute all analytics queries"""
        logger.info("=" * 70)
        logger.info("DATA VAULT ANALYTICS")
        logger.info("=" * 70)
        
        print("\n=== Current Customer View (Sample) ===")
        self.get_current_customer_view().head(10)
        
        print("\n=== Sales by Customer Segment ===")
        self.sales_by_customer_segment()
        
        print("\n=== Top Products ===")
        self.top_products_by_category()
        
        print("\n=== Recent Sales with Context ===")
        self.get_sales_with_context(20).head(10)

if __name__ == "__main__":
    analytics = DataVaultAnalytics()
    analytics.run_all_analytics()
```

---

## 6. USAGE GUIDE

### Installation & Setup

```bash
# 1. Install dependencies
pip install pandas sqlalchemy pymysql faker

# 2. Update configuration
# Edit dv_config.py with your database credentials

# 3. Create database
mysql -u root -p -e "CREATE DATABASE retail_dv;"

# 4. Run schema creation
mysql -u root -p retail_dv < schema.sql
```

### Running the Pipeline

```python
# Full load
from dv_etl_pipeline import DataVaultETL

pipeline = DataVaultETL()
results = pipeline.run_full_load(
    use_sample_data=True,  # Generate sample data
    build_pit=True         # Build PIT tables
)

# Incremental load
import pandas as pd
new_transactions = pd.read_csv('new_data.csv')
pipeline.run_incremental_load(new_transactions)

# Run analytics
from dv_queries import DataVaultAnalytics
analytics = DataVaultAnalytics()
analytics.run_all_analytics()
```

---

## 7. DATA VAULT ADVANTAGES

### vs. Dimensional Modeling

| Aspect | Data Vault | Dimensional Model |
|--------|------------|------------------|
| **Flexibility** | Easy to add sources | Requires redesign |
| **History** | Complete audit trail | Limited history (SCD) |
| **Loading** | Parallel loading | Sequential dependencies |
| **Agility** | Change-resilient | Change-sensitive |
| **Query Speed** | Requires joins | Fast (denormalized) |
| **Use Case** | Enterprise DW | Departmental marts |

### Key Benefits

1. **Auditability**: Every change tracked with load dates
2. **Scalability**: Parallel loading of hubs, links, satellites
3. **Flexibility**: Add new sources without redesigning
4. **Compliance**: Full data lineage and history
5. **Agile**: Iterative development approach

---

## 8. BEST PRACTICES

### Data Vault 2.0 Principles

1. **Hash Keys**: Always use MD5/SHA1 for consistency
2. **Immutable**: Never update/delete raw vault data
3. **Separation**: Keep business rules in business vault
4. **Parallel**: Load hubs/links/satellites independently
5. **PIT Tables**: Build for query optimization
6. **Naming**: Consistent naming conventions

### Performance Optimization

```sql
-- Index Strategy
CREATE INDEX idx_sat_load_end ON sat_customer_details(load_end_date);
CREATE INDEX idx_sat_hash_diff ON sat_customer_details(hash_diff);
CREATE INDEX idx_hub_business_key ON hub_customer(customer_id);

-- Partition Strategy (for large tables)
ALTER TABLE sat_sales_metrics 
PARTITION BY RANGE (YEAR(load_date)) (
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026)
);
```

---

## 9. TROUBLESHOOTING

### Common Issues

**Issue**: Slow satellite queries
- **Solution**: Use PIT tables, create proper indexes on load_end_date

**Issue**: Hash key collisions
- **Solution**: Use SHA-256 instead of MD5, ensure proper concatenation

**Issue**: Duplicate records in hubs
- **Solution**: Verify hash key generation, check for case sensitivity

**Issue**: PIT table build is slow
- **Solution**: Build incrementally, only for date ranges needed

---

## 10. ADVANCED FEATURES

### Multi-Active Satellites

For attributes with multiple concurrent values:

```python
# Example: Customer with multiple phone numbers
CREATE TABLE sat_customer_phone_ma (
    hub_customer_hk CHAR(32),
    phone_number VARCHAR(20),  -- Part of PK
    load_date TIMESTAMP,
    load_end_date TIMESTAMP,
    phone_type VARCHAR(20),  -- Mobile, Home, Work
    PRIMARY KEY (hub_customer_hk, phone_number, load_date)
);
```

### Bridge Tables

For complex many-to-many with attributes:

```python
# Bridge between Customer and Product for preferences
CREATE TABLE bridge_customer_product_preference (
    bridge_hk CHAR(32) PRIMARY KEY,
    hub_customer_hk CHAR(32),
    hub_product_hk CHAR(32),
    preference_score INT,
    load_date TIMESTAMP
);
```

---

## SUMMARY

This Data Vault 2.0 implementation provides:

✅ **Complete DV 2.0 Architecture**: Hubs, Links, Satellites
✅ **Hash Key Generation**: MD5/SHA1 for all entities  
✅ **Change Tracking**: Full historical tracking with hash diffs
✅ **Parallel Loading**: Independent loading of all structures
✅ **Point-in-Time Tables**: Query optimization
✅ **Time Travel Queries**: Query data as-of any date
✅ **Complete ETL Pipeline**: Extract, transform, load orchestration
✅ **Production-Ready**: Error handling, logging, batch management

**Key Differences from Dimensional Model:**
- More flexible and auditable
- Better for enterprise-scale warehouses
- Requires more complex queries (solved with PIT/Bridge)
- Ideal for regulatory compliance and data lineage(f"Inserted {len(df_new)} new records into hub_{hub_name}")
        else:
            logger.info(f"No new records for hub_{hub_name}")
        
        return len(df_new)
    
    def load_hub_customer(self, df: pd.DataFrame) -> int:
        """Load customer hub"""
        return self.load_hub(df, 'customer', 'customer_id')
    
    def load_hub_product(self, df: pd.DataFrame) -> int:
        """Load product hub"""
        return self.load_hub(df, 'product', 'product_id')
    
    def load_hub_store(self, df: pd.DataFrame) -> int:
        """Load store hub"""
        return self.load_hub(df, 'store', 'store_id')
    
    def load_hub_transaction(self, df: pd.DataFrame) -> int:
        """Load transaction hub"""
        return self.load_hub(df, 'transaction', 'transaction_id')
    
    def load_hub_promotion(self, df: pd.DataFrame) -> int:
        """Load promotion hub"""
        return self.load_hub(df, 'promotion', 'promotion_id')
    
    def load_all_hubs_parallel(self, data_dict: dict):
        """Load all hubs in parallel"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        hub_configs = [
            ('customer', 'customer_id', data_dict.get('customers')),
            ('product', 'product_id', data_dict.get('products')),
            ('store', 'store_id', data_dict.get('stores')),
            ('transaction', 'transaction_id', data_dict.get('transactions')),
            ('promotion', 'promotion_id', data_dict.get('promotions'))
        ]
        
        results = {}
        with ThreadPoolExecutor(max_workers=dv_config.max_workers) as executor:
            futures = {}
            for hub_name, bk_col, df in hub_configs:
                if df is not None and len(df) > 0:
                    future = executor.submit(self.load_hub, df, hub_name, bk_col)
                    futures[future] = hub_name
            
            for future in as_completed(futures):
                hub_name = futures[future]
                try:
                    count = future.result()
                    results[hub_name] = count
                    logger.info(f"Hub {hub_name} loaded: {count} records")
                except Exception as e:
                    logger.error(f"Error loading hub {hub_name}: {e}")
                    results[hub_name] = 0
        
        return results
```

### 5.4 Link Loader Module

```python
# dv_link_loader.py
"""
Link table loading for Data Vault
"""
import pandas as pd
from datetime import datetime
import logging
from dv_hash import hash_gen
from dv_config import dv_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LinkLoader:
    """Load Link tables in Data Vault"""
    
    def __init__(self, db_manager, record_source=None):
        self.db = db_manager
        self.record_source = record_source or dv_config.record_source
    
    def load_link_sales(self, df: pd.DataFrame) -> int:
        """
        Load sales link (Customer-Product-Store-Transaction-Promotion)
        """
        logger.info("Loading link_sales...")
        
        # Ensure we have necessary business keys
        required_cols = ['customer_id', 'product_id', 'store_id', 
                        'transaction_id', 'promotion_id']
        
        df_link = df[required_cols].copy()
        
        # Generate hub hash keys
        df_link = hash_gen.add_hub_hash_key(df_link, 'customer_id', 'customer')
        df_link = hash_gen.add_hub_hash_key(df_link, 'product_id', 'product')
        df_link = hash_gen.add_hub_hash_key(df_link, 'store_id', 'store')
        df_link = hash_gen.add_hub_hash_key(df_link, 'transaction_id', 'transaction')
        df_link = hash_gen.add_hub_hash_key(df_link, 'promotion_id', 'promotion')
        
        # Generate link hash key from all hub keys
        hub_key_cols = ['hub_customer_hk', 'hub_product_hk', 'hub_store_hk', 
                       'hub_transaction_hk', 'hub_promotion_hk']
        df_link = hash_gen.add_link_hash_key(df_link, hub_key_cols, 'sales')
        
        # Add metadata
        df_link['load_date'] = datetime.now()
        df_link['record_source'] = self.record_source
        
        # Remove duplicates
        df_link = df_link.drop_duplicates(subset=['link_sales_hk'])
        
        # Check existing records
        existing_query = "SELECT link_sales_hk FROM link_sales"
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
            existing_keys = set(df_existing['link_sales_hk'])
        except:
            existing_keys = set()
        
        # Filter to only new records
        df_new = df_link[~df_link['link_sales_hk'].isin(existing_keys)]
        
        if len(df_new) > 0:
            # Select columns for link table
            columns = ['link_sales_hk'] + hub_key_cols + ['load_date', 'record_source']
            df_new = df_new[columns]
            
            # Insert new records
            self.db.bulk_insert(df_new, 'link_sales', if_exists='append')
            logger.info(f"Inserted {len(df_new)} new records into link_sales")
        else:
            logger.info("No new records for link_sales")
        
        return len(df_new)
    
    def load_link_product_promotion(self, df: pd.DataFrame) -> int:
        """
        Load product-promotion link
        """
        logger.info("Loading link_product_promotion...")
        
        # Filter to only records with promotions
        df_link = df[df['promotion_id'] != 'PROMO000'][['product_id', 'promotion_id']].copy()
        
        if len(df_link) == 0:
            logger.info("No product-promotion links to load")
            return 0
        
        # Generate hub hash keys
        df_link = hash_gen.add_hub_hash_key(df_link, 'product_id', 'product')
        df_link = hash_gen.add_hub_hash_key(df_link, 'promotion_id', 'promotion')
        
        # Generate link hash key
        hub_key_cols = ['hub_product_hk', 'hub_promotion_hk']
        df_link = hash_gen.add_link_hash_key(df_link, hub_key_cols, 'product_promotion')
        
        # Add metadata
        df_link['load_date'] = datetime.now()
        df_link['record_source'] = self.record_source
        
        # Remove duplicates
        df_link = df_link.drop_duplicates(subset=['link_product_promotion_hk'])
        
        # Check existing records
        existing_query = "SELECT link_product_promotion_hk FROM link_product_promotion"
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
            existing_keys = set(df_existing['link_product_promotion_hk'])
        except:
            existing_keys = set()
        
        # Filter to only new records
        df_new = df_link[~df_link['link_product_promotion_hk'].isin(existing_keys)]
        
        if len(df_new) > 0:
            columns = ['link_product_promotion_hk'] + hub_key_cols + ['load_date', 'record_source']
            df_new = df_new[columns]
            
            self.db.bulk_insert(df_new, 'link_product_promotion', if_exists='append')
            logger.info(f"Inserted {len(df_new)} new records into link_product_promotion")
        else:
            logger.info("No new records for link_product_promotion")
        
        return len(df_new)
```

### 5.5 Satellite Loader Module

```python
# dv_satellite_loader.py
"""
Satellite table loading for Data Vault
"""
import pandas as pd
from datetime import datetime
import logging
from dv_hash import hash_gen
from dv_config import dv_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SatelliteLoader:
    """Load Satellite tables in Data Vault"""
    
    def __init__(self, db_manager, record_source=None):
        self.db = db_manager
        self.record_source = record_source or dv_config.record_source
    
    def load_satellite(self, df: pd.DataFrame, sat_name: str, 
                      hub_or_link_name: str, business_key_col: str,
                      attribute_cols: list, is_link_sat: bool = False) -> int:
        """
        Generic satellite loading with change detection
        
        Args:
            df: Source DataFrame
            sat_name: Satellite table name
            hub_or_link_name: Parent hub or link name
            business_key_col: Business key column name
            attribute_cols: List of attribute columns to track
            is_link_sat: True if satellite attached to link
        
        Returns:
            Number of records inserted
        """
        logger.info(f"Loading {sat_name}...")
        
        # Prepare satellite data
        df_sat = df[[business_key_col] + attribute_cols].drop_duplicates().copy()
        
        # Generate hash key for parent hub/link
        if is_link_sat:
            # For link satellites, need to generate link hash key
            # This is simplified - in practice, you'd need all hub keys
            hash_key_col = f"link_{hub_or_link_name}_hk"
            # Generate from business key (simplified)
            df_sat[hash_key_col] = df_sat[business_key_col].apply(
                lambda x: hash_gen.generate_hash_key(x)
            )
        else:
            df_sat = hash_gen.add_hub_hash_key(
                df_sat, business_key_col, hub_or_link_name
            )
            hash_key_col = f"hub_{hub_or_link_name}_hk"
        
        # Generate hash diff for change detection
        df_sat = hash_gen.add_hash_diff(df_sat, attribute_cols)
        
        # Add metadata
        df_sat['load_date'] = datetime.now()
        df_sat['load_end_date'] = None
        df_sat['record_source'] = self.record_source
        
        # Get existing satellite records
        existing_query = f"""
        SELECT {hash_key_col}, hash_diff, load_date
        FROM {sat_name}
        WHERE load_end_date IS NULL
        """
        
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
        except:
            df_existing = pd.DataFrame()
        
        new_records = []
        updated_count = 0
        
        for _, new_row in df_sat.iterrows():
            hk = new_row[hash_key_col]
            new_hash_diff = new_row['hash_diff']
            
            if len(df_existing) > 0:
                existing = df_existing[df_existing[hash_key_col] == hk]
            else:
                existing = pd.DataFrame()
            
            if len(existing) == 0:
                # New record
                new_records.append(new_row)
            else:
                # Check if changed
                existing_hash_diff = existing.iloc[0]['hash_diff']
                
                if new_hash_diff != existing_hash_diff:
                    # Close existing record
                    existing_load_date = existing.iloc[0]['load_date']
                    close_query = f"""
                    UPDATE {sat_name}
                    SET load_end_date = '{datetime.now()}'
                    WHERE {hash_key_col} = '{hk}' 
                    AND load_date = '{existing_load_date}'
                    """
                    self.db.execute_query(close_query)
                    
                    # Insert new version
                    new_records.append(new_row)
                    updated_count += 1
        
        if new_records:
            df_new = pd.DataFrame(new_records)
            
            # Select columns for satellite table
            columns = [hash_key_col, 'load_date', 'load_end_date', 'hash_diff', 
                      'record_source'] + attribute_cols
            df_new = df_new[columns]
            
            self.db.bulk_insert(df_new, sat_name, if_exists='append')
            logger.info(f"Inserted {len(df_new)} records into {sat_name} "
                       f"({updated_count} updates, {len(df_new)-updated_count} new)")
        else:
            logger.info(f"No changes detected for {sat_name}")
        
        return len(new_records)
    
    def load_sat_customer_details(self, df: pd.DataFrame) -> int:
        """Load customer details satellite"""
        attribute_cols = ['first_name', 'last_name', 'birth_date', 
                         'gender', 'customer_segment', 'registration_date']
        return self.load_satellite(
            df, 'sat_customer_details', 'customer', 
            'customer_id', attribute_cols
        )
    
    def load_sat_customer_contact(self, df: pd.DataFrame) -> int:
        """Load customer contact satellite"""
        attribute_cols = ['email', 'phone', 'address', 'city', 
                         'state', 'country', 'postal_code']
        return self.load_satellite(
            df, 'sat_customer_contact', 'customer',
            'customer_id', attribute_cols
        )
    
    def load_sat_product_details(self, df: pd.DataFrame) -> int:
        """Load product details satellite"""
        attribute_cols = ['product_name', 'category', 'subcategory', 
                         'brand', 'supplier']
        return self.load_satellite(
            df, 'sat_product_details', 'product',
            'product_id', attribute_cols
        )
    
    def load_sat_product_pricing(self, df: pd.DataFrame) -> int:
        """Load product pricing satellite"""
        attribute_cols = ['unit_cost', 'unit_price']
        # Add currency if not present
        if 'currency' not in df.columns:
            df['currency'] = 'USD'
        attribute_cols.append('currency')
        
        return self.load_satellite(
            df, 'sat_product_pricing', 'product',
            'product_id', attribute_cols
        )
    
    def load_sat_store_details(self, df: pd.DataFrame) -> int:
        """Load store details satellite"""
        attribute_cols = ['store_name', 'store_type', 'manager', 'address',
                         'city', 'state', 'country', 'postal_code', 'phone',
                         'open_date', 'square_footage', 'number_of_employees']
        return self.load_satellite(
            df, 'sat_store_details', 'store',
            'store_id', attribute_cols
        )
    
    def load_sat_transaction_details(self, df: pd.DataFrame) -> int:
        """Load transaction details satellite"""
        # Add time if not present
        if 'transaction_time' not in df.columns:
            df['transaction_time'] = '00:00:00'
        if 'payment_method' not in df.columns:
            df['payment_method'] = 'CARD'
        
        attribute_cols = ['transaction_date', 'transaction_time', 'payment_method']
        return self.load_satellite(
            df, 'sat_transaction_details', 'transaction',
            'transaction_id', attribute_cols
        )
    
    def load_sat_promotion_details(self, df: pd.DataFrame) -> int:
        """Load promotion details satellite"""
        attribute_cols = ['promotion_name', 'promotion_type', 'discount_percentage',
                         'start_date', 'end_date', 'description']
        return self.load_satellite(
            df, 'sat_promotion_details', 'promotion',
            'promotion_id', attribute_cols
        )
    
    def load_sat_sales_metrics(self, df: pd.DataFrame) -> int:
        """Load sales metrics satellite (attached to link)"""
        logger.info("Loading sat_sales_metrics...")
        
        # Prepare data with necessary keys
        df_sat = df.copy()
        
        # Generate all hub keys needed for link
        df_sat = hash_gen.add_hub_hash_key(df_sat, 'customer_id', 'customer')
        df_sat = hash_gen.add_hub_hash_key(df_sat, 'product_id', 'product')
        df_sat = hash_gen.add_hub_hash_key(df_sat, 'store_id', 'store')
        df_sat = hash_gen.add_hub_hash_key(df_sat, 'transaction_id', 'transaction')
        df_sat = hash_gen.add_hub_hash_key(df_sat, 'promotion_id', 'promotion')
        
        # Generate link hash key
        hub_key_cols = ['hub_customer_hk', 'hub_product_hk', 'hub_store_hk',
                       'hub_transaction_hk', 'hub_promotion_hk']
        df_sat = hash_gen.add_link_hash_key(df_sat, hub_key_cols, 'sales')
        
        # Satellite attributes
        attribute_cols = ['line_item_number', 'quantity', 'unit_price', 
                         'discount_amount', 'tax_amount', 'total_amount']
        
        # Calculate cost and profit if not present
        if 'cost' not in df_sat.columns:
            # Get product costs
            product_costs = pd.read_sql(
                "SELECT product_id, unit_cost FROM sat_product_pricing WHERE load_end_date IS NULL",
                self.db.engine
            )
            df_sat = df_sat.merge(product_costs, on='product_id', how='left')
            df_sat['cost'] = df_sat['unit_cost'].fillna(0) * df_sat['quantity']
        
        if 'profit' not in df_sat.columns:
            df_sat['profit'] = df_sat['total_amount'] - df_sat['cost']
        
        attribute_cols.extend(['cost', 'profit'])
        
        # Generate hash diff
        df_sat = hash_gen.add_hash_diff(df_sat, attribute_cols)
        
        # Add metadata
        df_sat['load_date'] = datetime.now()
        df_sat['load_end_date'] = None
        df_sat['record_source'] = self.record_source
        
        # For sales metrics, we typically don't update (immutable facts)
        # So we just insert new records
        
        # Check existing
        existing_query = "SELECT link_sales_hk FROM sat_sales_metrics WHERE load_end_date IS NULL"
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
            existing_keys = set(df_existing['link_sales_hk'])
        except:
            existing_keys = set()
        
        df_new = df_sat[~df_sat['link_sales_hk'].isin(existing_keys)]
        
        if len(df_new) > 0:
            columns = ['link_sales_hk', 'load_date', 'load_end_date', 'hash_diff',
                      'record_source'] + attribute_cols
            df_new = df_new[columns]
            
            self.db.bulk_insert(df_new, 'sat_sales_metrics', if_exists='append')
            logger.info(f"Inserted {len(df_new)} records into sat_sales_metrics")
        else:
            logger.info("No new records for sat_sales_metrics")
        
        return len(df_new)
```

### 5.6 Point-in-Time (PIT) Builder

```python
# dv_pit_builder.py
"""
Point-in-Time table builder for Data Vault query optimization
"""
import pandas as pd
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PITBuilder:
    """Build Point-in-Time tables for efficient querying"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def build_pit_customer(self, start_date=None, end_date=None):
        """
        Build PIT table for customer
        """
        logger.info("Building pit_customer...")
        
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=365)).date()
        if end_date is None:
            end_date = datetime.now().date()
        
        # Get all customer hub keys
        df_customers = pd.read_sql("SELECT hub_customer_hk FROM hub_customer", 
                                  self.db.engine)
        
        # Generate date range
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        pit_records = []
        
        for customer_hk in df_customers['hub_customer_hk']:
            for snapshot_date in dates:
                # Find latest satellite record before snapshot date
                query_details = f"""
                SELECT load_date 
                FROM sat_customer_details
                WHERE hub_customer_hk = '{customer_hk}'
                AND load_date <= '{snapshot_date}'
                ORDER BY load_date DESC
                LIMIT 1
                """
                
                query_contact = f"""
                SELECT load_date
                FROM sat_customer_contact
                WHERE hub_customer_hk = '{customer_hk}'
                AND load_date <= '{snapshot_date}'
                ORDER BY load_date DESC
                LIMIT 1
                """
                
                try:
                    details_load = pd.read_sql(query_details, self.db.engine)
                    contact_load = pd.read_sql(query_contact, self.db.engine)
                    
                    details_date = details_load.iloc[0]['load_date'] if len(details_load) > 0 else None
                    contact_date = contact_load.iloc[0]['load_date'] if len(contact_load) > 0 else None
                    
                    if details_date or contact_date:
                        pit_records.append({
                            'hub_customer_hk': customer_hk,
                            'snapshot_date': snapshot_date.date(),
                            'sat_customer_details_load_date': details_date,
                            'sat_customer_contact_load_date': contact_date
                        })
                except:
                    continue
        
        if pit_records:
            df_pit = pd.DataFrame(pit_records)
            
            # Clear existing PIT data
            self.db.truncate_table('pit_customer')
            
            # Load new PIT data
            self.db.bulk_insert(df_pit, 'pit_customer', if_exists='append')
            logger.info