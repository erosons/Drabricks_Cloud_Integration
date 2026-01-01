# Complete End-to-End Data Warehouse Implementation

## Business Scenario: Retail Sales Analytics

We'll build a data warehouse for a retail company to analyze sales, customers, and products across multiple stores.

---

## 1. CONCEPTUAL DESIGN

### Business Requirements
- **Subject Areas**: Sales, Customers, Products, Stores
- **Key Metrics**: Revenue, Units Sold, Profit, Customer Lifetime Value
- **Dimensions**: Time, Customer, Product, Store, Promotion
- **Grain**: Individual transaction line items

### High-Level Architecture
```
Source Systems → Staging Area → Data Warehouse → Data Marts → BI Tools
     (OLTP)         (ETL)        (Star Schema)      (Cubes)    (Reports)
```

### Conceptual Entities
1. **Sales Transactions** - Core business events
2. **Customers** - Who is buying
3. **Products** - What is being sold
4. **Stores** - Where sales occur
5. **Time** - When transactions happen
6. **Promotions** - Marketing campaigns

---

## 2. LOGICAL DESIGN

### Star Schema Model

**Fact Table**: `fact_sales`
- Grain: One row per product sold in a transaction
- Measures: quantity, unit_price, discount_amount, tax_amount, total_amount, cost, profit
- Foreign Keys: date_key, customer_key, product_key, store_key, promotion_key

**Dimension Tables**:

1. **dim_date**
   - date_key (PK), full_date, year, quarter, month, day, day_of_week, is_weekend, is_holiday

2. **dim_customer**
   - customer_key (PK), customer_id (NK), first_name, last_name, email, phone, birth_date, gender, customer_segment, registration_date, city, state, country

3. **dim_product**
   - product_key (PK), product_id (NK), product_name, category, subcategory, brand, unit_cost, unit_price, supplier

4. **dim_store**
   - store_key (PK), store_id (NK), store_name, store_type, manager, address, city, state, country, open_date, square_footage

5. **dim_promotion**
   - promotion_key (PK), promotion_id (NK), promotion_name, promotion_type, discount_percentage, start_date, end_date

### Slowly Changing Dimension (SCD) Strategy
- **dim_customer**: SCD Type 2 (track historical changes for segment)
- **dim_product**: SCD Type 2 (track price changes)
- **dim_store**: SCD Type 1 (overwrite non-critical changes)
- **dim_promotion**: SCD Type 0 (no changes allowed)

---

## 3. PHYSICAL IMPLEMENTATION

### Database Schema (PostgreSQL/MySQL)

```sql
-- =====================================================
-- DATA WAREHOUSE PHYSICAL IMPLEMENTATION
-- =====================================================

-- Drop existing tables
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_store;
DROP TABLE IF EXISTS dim_promotion;

-- =====================================================
-- DIMENSION TABLES
-- =====================================================

-- Date Dimension
CREATE TABLE dim_date (
    date_key INT PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month INT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    day INT NOT NULL,
    day_of_week INT NOT NULL,
    day_name VARCHAR(20) NOT NULL,
    week_of_year INT NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_holiday BOOLEAN DEFAULT FALSE,
    holiday_name VARCHAR(100),
    fiscal_year INT,
    fiscal_quarter INT
);

CREATE INDEX idx_date_full_date ON dim_date(full_date);
CREATE INDEX idx_date_year_month ON dim_date(year, month);

-- Customer Dimension (SCD Type 2)
CREATE TABLE dim_customer (
    customer_key INT PRIMARY KEY AUTO_INCREMENT,
    customer_id VARCHAR(50) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(20),
    birth_date DATE,
    gender VARCHAR(10),
    customer_segment VARCHAR(50),
    registration_date DATE,
    address VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),
    
    -- SCD Type 2 columns
    effective_date DATE NOT NULL,
    expiration_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    
    UNIQUE KEY uk_customer_id_effective (customer_id, effective_date)
);

CREATE INDEX idx_customer_id ON dim_customer(customer_id);
CREATE INDEX idx_customer_current ON dim_customer(is_current);

-- Product Dimension (SCD Type 2)
CREATE TABLE dim_product (
    product_key INT PRIMARY KEY AUTO_INCREMENT,
    product_id VARCHAR(50) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    unit_cost DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    supplier VARCHAR(255),
    
    -- SCD Type 2 columns
    effective_date DATE NOT NULL,
    expiration_date DATE,
    is_current BOOLEAN DEFAULT TRUE,
    
    UNIQUE KEY uk_product_id_effective (product_id, effective_date)
);

CREATE INDEX idx_product_id ON dim_product(product_id);
CREATE INDEX idx_product_category ON dim_product(category, subcategory);
CREATE INDEX idx_product_current ON dim_product(is_current);

-- Store Dimension (SCD Type 1)
CREATE TABLE dim_store (
    store_key INT PRIMARY KEY AUTO_INCREMENT,
    store_id VARCHAR(50) NOT NULL UNIQUE,
    store_name VARCHAR(255) NOT NULL,
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
    number_of_employees INT
);

CREATE INDEX idx_store_id ON dim_store(store_id);
CREATE INDEX idx_store_location ON dim_store(city, state);

-- Promotion Dimension (SCD Type 0)
CREATE TABLE dim_promotion (
    promotion_key INT PRIMARY KEY AUTO_INCREMENT,
    promotion_id VARCHAR(50) NOT NULL UNIQUE,
    promotion_name VARCHAR(255) NOT NULL,
    promotion_type VARCHAR(50),
    discount_percentage DECIMAL(5,2),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    description TEXT
);

CREATE INDEX idx_promotion_id ON dim_promotion(promotion_id);
CREATE INDEX idx_promotion_dates ON dim_promotion(start_date, end_date);

-- =====================================================
-- FACT TABLE
-- =====================================================

CREATE TABLE fact_sales (
    sales_key BIGINT PRIMARY KEY AUTO_INCREMENT,
    
    -- Foreign Keys (Dimension Keys)
    date_key INT NOT NULL,
    customer_key INT NOT NULL,
    product_key INT NOT NULL,
    store_key INT NOT NULL,
    promotion_key INT DEFAULT 1, -- 1 = No Promotion
    
    -- Degenerate Dimensions
    transaction_id VARCHAR(50) NOT NULL,
    line_item_number INT NOT NULL,
    
    -- Measures (Additive)
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0,
    tax_amount DECIMAL(10,2) DEFAULT 0,
    total_amount DECIMAL(10,2) NOT NULL,
    cost DECIMAL(10,2) NOT NULL,
    profit DECIMAL(10,2) NOT NULL,
    
    -- ETL Metadata
    etl_batch_id INT,
    etl_insert_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign Key Constraints
    FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
    FOREIGN KEY (customer_key) REFERENCES dim_customer(customer_key),
    FOREIGN KEY (product_key) REFERENCES dim_product(product_key),
    FOREIGN KEY (store_key) REFERENCES dim_store(store_key),
    FOREIGN KEY (promotion_key) REFERENCES dim_promotion(promotion_key),
    
    UNIQUE KEY uk_transaction_line (transaction_id, line_item_number)
);

-- Fact Table Indexes (Critical for Query Performance)
CREATE INDEX idx_fact_date ON fact_sales(date_key);
CREATE INDEX idx_fact_customer ON fact_sales(customer_key);
CREATE INDEX idx_fact_product ON fact_sales(product_key);
CREATE INDEX idx_fact_store ON fact_sales(store_key);
CREATE INDEX idx_fact_promotion ON fact_sales(promotion_key);
CREATE INDEX idx_fact_transaction ON fact_sales(transaction_id);
CREATE INDEX idx_fact_composite ON fact_sales(date_key, store_key, product_key);

-- =====================================================
-- STAGING TABLES
-- =====================================================

CREATE TABLE stg_transactions (
    transaction_id VARCHAR(50),
    transaction_date DATE,
    customer_id VARCHAR(50),
    product_id VARCHAR(50),
    store_id VARCHAR(50),
    promotion_id VARCHAR(50),
    quantity INT,
    unit_price DECIMAL(10,2),
    discount_amount DECIMAL(10,2),
    tax_amount DECIMAL(10,2),
    line_item_number INT,
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- AGGREGATED FACT TABLES (Optional)
-- =====================================================

CREATE TABLE fact_sales_daily (
    date_key INT NOT NULL,
    store_key INT NOT NULL,
    product_key INT NOT NULL,
    total_quantity INT,
    total_revenue DECIMAL(15,2),
    total_profit DECIMAL(15,2),
    transaction_count INT,
    PRIMARY KEY (date_key, store_key, product_key)
);
```

---

## 4. ETL WORKFLOW IMPLEMENTATION

### ETL Architecture

```
Extract → Transform → Load
   ↓          ↓         ↓
Source    Staging    Target
 OLTP      Area       DW
```

### Python Requirements

```
# requirements.txt
pandas>=2.0.0
sqlalchemy>=2.0.0
pymysql>=1.0.0
psycopg2-binary>=2.9.0
python-dateutil>=2.8.0
faker>=18.0.0
```

---

## 5. PYTHON IMPLEMENTATION

### 5.1 Configuration Module

```python
# config.py
"""
Configuration for Data Warehouse ETL
"""
from dataclasses import dataclass
from datetime import datetime

@dataclass
class DatabaseConfig:
    """Database connection configuration"""
    host: str = 'localhost'
    port: int = 3306
    database: str = 'retail_dw'
    username: str = 'etl_user'
    password: str = 'etl_password'
    
    def get_connection_string(self):
        return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class ETLConfig:
    """ETL process configuration"""
    batch_size: int = 1000
    log_level: str = 'INFO'
    staging_schema: str = 'staging'
    target_schema: str = 'dw'
    
    # Source system paths
    source_transactions: str = 'data/transactions.csv'
    source_customers: str = 'data/customers.csv'
    source_products: str = 'data/products.csv'
    source_stores: str = 'data/stores.csv'
    
    # Date configuration
    start_date: str = '2023-01-01'
    end_date: str = '2024-12-31'

# Global configurations
db_config = DatabaseConfig()
etl_config = ETLConfig()
```

### 5.2 Database Connection Module

```python
# db_connection.py
"""
Database connection and utility functions
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import logging
from config import db_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and operations"""
    
    def __init__(self, config=db_config):
        self.config = config
        self.engine = None
        self.session_factory = None
        
    def connect(self):
        """Create database connection"""
        try:
            connection_string = self.config.get_connection_string()
            self.engine = create_engine(
                connection_string,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False
            )
            self.session_factory = sessionmaker(bind=self.engine)
            logger.info("Database connection established")
            return self.engine
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """Context manager for database sessions"""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()
    
    def execute_query(self, query, params=None):
        """Execute a query and return results"""
        with self.engine.connect() as conn:
            result = conn.execute(text(query), params or {})
            conn.commit()
            return result
    
    def bulk_insert(self, df, table_name, if_exists='append'):
        """Bulk insert DataFrame into table"""
        try:
            df.to_sql(
                table_name,
                self.engine,
                if_exists=if_exists,
                index=False,
                chunksize=1000
            )
            logger.info(f"Inserted {len(df)} rows into {table_name}")
        except Exception as e:
            logger.error(f"Bulk insert failed: {e}")
            raise
    
    def truncate_table(self, table_name):
        """Truncate a table"""
        query = f"TRUNCATE TABLE {table_name}"
        self.execute_query(query)
        logger.info(f"Truncated table: {table_name}")
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

# Global database manager instance
db_manager = DatabaseManager()
```

### 5.3 Data Generation Module (for testing)

```python
# data_generator.py
"""
Generate sample data for testing ETL pipeline
"""
import pandas as pd
import numpy as np
from faker import Faker
from datetime import datetime, timedelta
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

fake = Faker()
Faker.seed(42)
np.random.seed(42)
random.seed(42)

class DataGenerator:
    """Generate sample retail data"""
    
    def __init__(self):
        self.customers = None
        self.products = None
        self.stores = None
        self.promotions = None
        
    def generate_customers(self, n=1000):
        """Generate customer data"""
        logger.info(f"Generating {n} customers...")
        
        segments = ['Gold', 'Silver', 'Bronze', 'New']
        genders = ['Male', 'Female', 'Other']
        
        data = []
        for i in range(n):
            customer_id = f"CUST{i+1:06d}"
            registration_date = fake.date_between(start_date='-3y', end_date='today')
            
            data.append({
                'customer_id': customer_id,
                'first_name': fake.first_name(),
                'last_name': fake.last_name(),
                'email': fake.email(),
                'phone': fake.phone_number()[:20],
                'birth_date': fake.date_of_birth(minimum_age=18, maximum_age=80),
                'gender': random.choice(genders),
                'customer_segment': random.choice(segments),
                'registration_date': registration_date,
                'address': fake.street_address(),
                'city': fake.city(),
                'state': fake.state(),
                'country': 'USA',
                'postal_code': fake.zipcode()
            })
        
        self.customers = pd.DataFrame(data)
        logger.info(f"Generated {len(self.customers)} customers")
        return self.customers
    
    def generate_products(self, n=500):
        """Generate product data"""
        logger.info(f"Generating {n} products...")
        
        categories = {
            'Electronics': ['Laptops', 'Phones', 'Tablets', 'Accessories'],
            'Clothing': ['Men', 'Women', 'Kids', 'Shoes'],
            'Home': ['Furniture', 'Decor', 'Kitchen', 'Bedding'],
            'Sports': ['Equipment', 'Apparel', 'Footwear', 'Accessories']
        }
        
        brands = ['BrandA', 'BrandB', 'BrandC', 'BrandD', 'BrandE']
        
        data = []
        for i in range(n):
            category = random.choice(list(categories.keys()))
            subcategory = random.choice(categories[category])
            unit_cost = round(random.uniform(10, 500), 2)
            unit_price = round(unit_cost * random.uniform(1.3, 2.5), 2)
            
            data.append({
                'product_id': f"PROD{i+1:06d}",
                'product_name': f"{fake.word().title()} {subcategory}",
                'category': category,
                'subcategory': subcategory,
                'brand': random.choice(brands),
                'unit_cost': unit_cost,
                'unit_price': unit_price,
                'supplier': fake.company()
            })
        
        self.products = pd.DataFrame(data)
        logger.info(f"Generated {len(self.products)} products")
        return self.products
    
    def generate_stores(self, n=20):
        """Generate store data"""
        logger.info(f"Generating {n} stores...")
        
        store_types = ['Superstore', 'Mall', 'Outlet', 'Express']
        
        data = []
        for i in range(n):
            data.append({
                'store_id': f"STORE{i+1:03d}",
                'store_name': f"{fake.city()} {random.choice(store_types)}",
                'store_type': random.choice(store_types),
                'manager': fake.name(),
                'address': fake.street_address(),
                'city': fake.city(),
                'state': fake.state(),
                'country': 'USA',
                'postal_code': fake.zipcode(),
                'phone': fake.phone_number()[:20],
                'open_date': fake.date_between(start_date='-10y', end_date='-1y'),
                'square_footage': random.randint(5000, 50000),
                'number_of_employees': random.randint(10, 200)
            })
        
        self.stores = pd.DataFrame(data)
        logger.info(f"Generated {len(self.stores)} stores")
        return self.stores
    
    def generate_promotions(self, n=50):
        """Generate promotion data"""
        logger.info(f"Generating {n} promotions...")
        
        promo_types = ['Percentage Off', 'Buy One Get One', 'Seasonal Sale', 'Clearance']
        
        data = [{
            'promotion_id': 'PROMO000',
            'promotion_name': 'No Promotion',
            'promotion_type': 'None',
            'discount_percentage': 0.00,
            'start_date': '2020-01-01',
            'end_date': '2099-12-31',
            'description': 'Default no promotion'
        }]
        
        for i in range(1, n+1):
            start_date = fake.date_between(start_date='-2y', end_date='+6m')
            end_date = start_date + timedelta(days=random.randint(7, 60))
            
            data.append({
                'promotion_id': f"PROMO{i:03d}",
                'promotion_name': f"{fake.word().title()} {random.choice(promo_types)}",
                'promotion_type': random.choice(promo_types),
                'discount_percentage': round(random.uniform(5, 50), 2),
                'start_date': start_date,
                'end_date': end_date,
                'description': fake.sentence()
            })
        
        self.promotions = pd.DataFrame(data)
        logger.info(f"Generated {len(self.promotions)} promotions")
        return self.promotions
    
    def generate_transactions(self, n=10000, start_date='2024-01-01', end_date='2024-12-31'):
        """Generate transaction data"""
        logger.info(f"Generating {n} transactions...")
        
        if self.customers is None:
            self.generate_customers()
        if self.products is None:
            self.generate_products()
        if self.stores is None:
            self.generate_stores()
        if self.promotions is None:
            self.generate_promotions()
        
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        data = []
        transaction_counter = 1
        
        for _ in range(n):
            # Random transaction date
            trans_date = start + (end - start) * random.random()
            trans_id = f"TRANS{transaction_counter:010d}"
            
            # Number of items in transaction
            num_items = random.randint(1, 5)
            
            # Select random customer, store
            customer = self.customers.sample(1).iloc[0]
            store = self.stores.sample(1).iloc[0]
            
            for line_num in range(1, num_items + 1):
                product = self.products.sample(1).iloc[0]
                
                # Check if promotion applies
                active_promos = self.promotions[
                    (pd.to_datetime(self.promotions['start_date']) <= trans_date) &
                    (pd.to_datetime(self.promotions['end_date']) >= trans_date) &
                    (self.promotions['promotion_id'] != 'PROMO000')
                ]
                
                if len(active_promos) > 0 and random.random() < 0.3:
                    promo = active_promos.sample(1).iloc[0]
                else:
                    promo = self.promotions[self.promotions['promotion_id'] == 'PROMO000'].iloc[0]
                
                quantity = random.randint(1, 5)
                unit_price = product['unit_price']
                
                # Calculate discount
                if promo['promotion_id'] != 'PROMO000':
                    discount_pct = promo['discount_percentage'] / 100
                    discount_amount = round(unit_price * quantity * discount_pct, 2)
                else:
                    discount_amount = 0.00
                
                subtotal = unit_price * quantity - discount_amount
                tax_amount = round(subtotal * 0.08, 2)
                total_amount = subtotal + tax_amount
                
                data.append({
                    'transaction_id': trans_id,
                    'transaction_date': trans_date.date(),
                    'customer_id': customer['customer_id'],
                    'product_id': product['product_id'],
                    'store_id': store['store_id'],
                    'promotion_id': promo['promotion_id'],
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'discount_amount': discount_amount,
                    'tax_amount': tax_amount,
                    'line_item_number': line_num
                })
            
            transaction_counter += 1
        
        transactions = pd.DataFrame(data)
        logger.info(f"Generated {len(transactions)} transaction line items")
        return transactions
    
    def save_all_data(self, output_dir='data'):
        """Generate and save all data to CSV files"""
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        self.generate_customers(1000).to_csv(f'{output_dir}/customers.csv', index=False)
        self.generate_products(500).to_csv(f'{output_dir}/products.csv', index=False)
        self.generate_stores(20).to_csv(f'{output_dir}/stores.csv', index=False)
        self.generate_promotions(50).to_csv(f'{output_dir}/promotions.csv', index=False)
        self.generate_transactions(10000).to_csv(f'{output_dir}/transactions.csv', index=False)
        
        logger.info(f"All data saved to {output_dir} directory")

if __name__ == "__main__":
    generator = DataGenerator()
    generator.save_all_data()
```

### 5.4 Dimension Loading Module

```python
# dimension_loader.py
"""
Load and manage dimension tables with SCD support
"""
import pandas as pd
from datetime import datetime, date
import logging
from db_connection import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DimensionLoader:
    """Handles loading of dimension tables"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        
    def load_date_dimension(self, start_date='2023-01-01', end_date='2025-12-31'):
        """Generate and load date dimension"""
        logger.info(f"Loading date dimension from {start_date} to {end_date}")
        
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        dates = pd.date_range(start, end, freq='D')
        
        date_data = []
        for dt in dates:
            date_key = int(dt.strftime('%Y%m%d'))
            
            date_data.append({
                'date_key': date_key,
                'full_date': dt.date(),
                'year': dt.year,
                'quarter': (dt.month - 1) // 3 + 1,
                'month': dt.month,
                'month_name': dt.strftime('%B'),
                'day': dt.day,
                'day_of_week': dt.dayofweek + 1,
                'day_name': dt.strftime('%A'),
                'week_of_year': dt.isocalendar()[1],
                'is_weekend': dt.dayofweek >= 5,
                'is_holiday': False,
                'holiday_name': None,
                'fiscal_year': dt.year if dt.month >= 7 else dt.year - 1,
                'fiscal_quarter': ((dt.month - 7) % 12) // 3 + 1
            })
        
        df_date = pd.DataFrame(date_data)
        self.db.truncate_table('dim_date')
        self.db.bulk_insert(df_date, 'dim_date', if_exists='append')
        logger.info(f"Loaded {len(df_date)} dates into dim_date")
        
        return df_date
    
    def load_customer_dimension_scd2(self, df_customers):
        """Load customer dimension with SCD Type 2"""
        logger.info(f"Loading {len(df_customers)} customers with SCD Type 2")
        
        # Get existing customers
        existing_query = "SELECT * FROM dim_customer WHERE is_current = TRUE"
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
        except:
            df_existing = pd.DataFrame()
        
        today = date.today()
        new_records = []
        
        for _, new_row in df_customers.iterrows():
            customer_id = new_row['customer_id']
            
            if len(df_existing) > 0:
                existing = df_existing[df_existing['customer_id'] == customer_id]
            else:
                existing = pd.DataFrame()
            
            if len(existing) == 0:
                # New customer - insert with current flag
                record = new_row.to_dict()
                record['effective_date'] = today
                record['expiration_date'] = None
                record['is_current'] = True
                new_records.append(record)
            else:
                # Check if customer_segment changed (tracked attribute)
                existing_record = existing.iloc[0]
                
                if new_row['customer_segment'] != existing_record['customer_segment']:
                    # Close old record
                    update_query = f"""
                    UPDATE dim_customer 
                    SET expiration_date = '{today}', is_current = FALSE
                    WHERE customer_key = {existing_record['customer_key']}
                    """
                    self.db.execute_query(update_query)
                    
                    # Insert new record
                    record = new_row.to_dict()
                    record['effective_date'] = today
                    record['expiration_date'] = None
                    record['is_current'] = True
                    new_records.append(record)
                    
                    logger.info(f"SCD2: Customer {customer_id} segment changed")
        
        if new_records:
            df_new = pd.DataFrame(new_records)
            df_new = df_new.drop(columns=['customer_key'], errors='ignore')
            self.db.bulk_insert(df_new, 'dim_customer', if_exists='append')
            logger.info(f"Inserted {len(df_new)} new customer records")
        
        return len(new_records)
    
    def load_product_dimension_scd2(self, df_products):
        """Load product dimension with SCD Type 2"""
        logger.info(f"Loading {len(df_products)} products with SCD Type 2")
        
        existing_query = "SELECT * FROM dim_product WHERE is_current = TRUE"
        try:
            df_existing = pd.read_sql(existing_query, self.db.engine)
        except:
            df_existing = pd.DataFrame()
        
        today = date.today()
        new_records = []
        
        for _, new_row in df_products.iterrows():
            product_id = new_row['product_id']
            
            if len(df_existing) > 0:
                existing = df_existing[df_existing['product_id'] == product_id]
            else:
                existing = pd.DataFrame()
            
            if len(existing) == 0:
                record = new_row.to_dict()
                record['effective_date'] = today
                record['expiration_date'] = None
                record['is_current'] = True
                new_records.append(record)
            else:
                existing_record = existing.iloc[0]
                
                # Track price changes
                if (new_row['unit_price'] != existing_record['unit_price'] or 
                    new_row['unit_cost'] != existing_record['unit_cost']):
                    
                    update_query = f"""
                    UPDATE dim_product 
                    SET expiration_date = '{today}', is_current = FALSE
                    WHERE product_key = {existing_record['product_key']}
                    """
                    self.db.execute_query(update_query)
                    
                    record = new_row.to_dict()
                    record['effective_date'] = today
                    record['expiration_date'] = None
                    record['is_current'] = True
                    new_records.append(record)
                    
                    logger.info(f"SCD2: Product {product_id} price changed")
        
        if new_records:
            df_new = pd.DataFrame(new_records)
            df_new = df_new.drop(columns=['product_key'], errors='ignore')
            self.db.bulk_insert(df_new, 'dim_product', if_exists='append')
            logger.info(f"Inserted {len(df_new)} new product records")
        
        return len(new_records)
    
    def load_store_dimension_scd1(self, df_stores):
        """Load store dimension with SCD Type 1 (overwrite)"""
        logger.info(f"Loading {len(df_stores)} stores with SCD Type 1")
        
        self.db.truncate_table('dim_store')
        df_stores = df_stores.drop(columns=['store_key'], errors='ignore')
        self.db.bulk_insert(df_stores, 'dim_store', if_exists='append')
        logger.info(f"Loaded {len(df_stores)} stores")
        
        return len(df_stores)
    
    def load_promotion_dimension(self, df_promotions):
        """Load promotion dimension (SCD Type 0 - no changes)"""
        logger.info(f"Loading {len(df_promotions)} promotions")
        
        self.db.truncate_table('dim_promotion')
        df_promotions = df_promotions.drop(columns=['promotion_key'], errors='ignore')
        self.db.bulk_insert(df_promotions, 'dim_promotion', if_exists='append')
        logger.info(f"Loaded {len(df_promotions)} promotions")
        
        return len(df_promotions)
```

### 5.5 Fact Table Loading Module

```python
# fact_loader.py
"""
Load fact tables with dimension key lookups
"""
import pandas as pd
import logging
from datetime import datetime
from db_connection import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FactLoader:
    """Handles loading of fact tables"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.dim_cache = {}
        
    def load_dimension_cache(self):
        """Cache dimension tables for lookups"""
        logger.info("Loading dimension caches...")
        
        # Cache current dimensions
        self.dim_cache['date'] = pd.read_sql(
            "SELECT date_key, full_date FROM dim_date", 
            self.db.engine
        )
        
        self.dim_cache['customer'] = pd.read_sql(
            "SELECT customer_key, customer_id FROM dim_customer WHERE is_current = TRUE",
            self.db.engine
        )
        
        self.dim_cache['product'] = pd.read_sql(
            "SELECT product_key, product_id FROM dim_product WHERE is_current = TRUE",
            self.db.engine
        )
        
        self.dim_cache['store'] = pd.read_sql(
            "SELECT store_key, store_id FROM dim_store",
            self.db.engine
        )
        
        self.dim_cache['promotion'] = pd.read_sql(
            "SELECT promotion_key, promotion_id FROM dim_promotion",
            self.db.engine
        )
        
        logger.info("Dimension caches loaded")
    
    def lookup_dimension_keys(self, df_transactions):
        """Add dimension keys to transaction data"""
        logger.info("Looking up dimension keys...")
        
        # Convert transaction_date to date_key format
        df_transactions['date_key'] = pd.to_datetime(
            df_transactions['transaction_date']
        ).dt.strftime('%Y%m%d').astype(int)
        
        # Merge with dimensions
        df = df_transactions.copy()
        
        # Date key
        df = df.merge(
            self.dim_cache['date'][['date_key']],
            on='date_key',
            how='left'
        )
        
        # Customer key
        df = df.merge(
            self.dim_cache['customer'],
            on='customer_id',
            how='left'
        )
        
        # Product key
        df = df.merge(
            self.dim_cache['product'],
            on='product_id',
            how='left'
        )
        
        # Store key
        df = df.merge(
            self.dim_cache['store'],
            on='store_id',
            how='left'
        )
        
        # Promotion key
        df = df.merge(
            self.dim_cache['promotion'],
            on='promotion_id',
            how='left'
        )
        
        # Check for missing keys
        missing_keys = df[['customer_key', 'product_key', 'store_key', 'promotion_key']].isnull().sum()
        if missing_keys.any():
            logger.warning(f"Missing dimension keys found:\n{missing_keys}")
        
        return df
    
    def calculate_measures(self, df):
        """Calculate fact table measures"""
        logger.info("Calculating measures...")
        
        # Get product costs from dimension
        product_costs = pd.read_sql(
            "SELECT product_id, unit_cost FROM dim_product WHERE is_current = TRUE",
            self.db.engine
        )
        
        df = df.merge(product_costs, on='product_id', how='left')
        
        # Calculate measures
        df['cost'] = df['unit_cost'] * df['quantity']
        df['total_amount'] = (df['unit_price'] * df['quantity'] - 
                             df['discount_amount'] + df['tax_amount'])
        df['profit'] = df['total_amount'] - df['cost']
        
        return df
    
    def load_fact_sales(self, df_transactions, batch_id=None):
        """Load sales fact table"""
        logger.info(f"Loading {len(df_transactions)} transactions to fact table")
        
        # Load dimension caches
        self.load_dimension_cache()
        
        # Lookup dimension keys
        df_fact = self.lookup_dimension_keys(df_transactions)
        
        # Calculate measures
        df_fact = self.calculate_measures(df_fact)
        
        # Select only fact table columns
        fact_columns = [
            'date_key', 'customer_key', 'product_key', 'store_key', 'promotion_key',
            'transaction_id', 'line_item_number', 'quantity', 'unit_price',
            'discount_amount', 'tax_amount', 'total_amount', 'cost', 'profit'
        ]
        
        df_fact = df_fact[fact_columns].copy()
        
        # Add ETL metadata
        if batch_id:
            df_fact['etl_batch_id'] = batch_id
        
        # Remove any rows with missing dimension keys
        df_fact = df_fact.dropna(subset=['customer_key', 'product_key', 'store_key'])
        
        # Load to database
        self.db.bulk_insert(df_fact, 'fact_sales', if_exists='append')
        logger.info(f"Loaded {len(df_fact)} rows to fact_sales")
        
        return len(df_fact)
    
    def build_daily_aggregates(self):
        """Build daily aggregated fact table"""
        logger.info("Building daily aggregates...")
        
        query = """
        INSERT INTO fact_sales_daily (
            date_key, store_key, product_key, 
            total_quantity, total_revenue, total_profit, transaction_count
        )
        SELECT 
            date_key,
            store_key,
            product_key,
            SUM(quantity) as total_quantity,
            SUM(total_amount) as total_revenue,
            SUM(profit) as total_profit,
            COUNT(DISTINCT transaction_id) as transaction_count
        FROM fact_sales
        GROUP BY date_key, store_key, product_key
        ON DUPLICATE KEY UPDATE
            total_quantity = VALUES(total_quantity),
            total_revenue = VALUES(total_revenue),
            total_profit = VALUES(total_profit),
            transaction_count = VALUES(transaction_count)
        """
        
        self.db.execute_query(query)
        logger.info("Daily aggregates built successfully")
```

### 5.6 Main ETL Orchestrator

```python
# etl_pipeline.py
"""
Main ETL pipeline orchestrator
"""
import pandas as pd
import logging
from datetime import datetime
from db_connection import db_manager
from dimension_loader import DimensionLoader
from fact_loader import FactLoader
from data_generator import DataGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ETLPipeline:
    """Main ETL pipeline orchestrator"""
    
    def __init__(self):
        self.db = db_manager
        self.dim_loader = DimensionLoader(db_manager)
        self.fact_loader = FactLoader(db_manager)
        self.batch_id = None
        
    def initialize(self):
        """Initialize database connection"""
        logger.info("=" * 60)
        logger.info("ETL PIPELINE INITIALIZATION")
        logger.info("=" * 60)
        
        self.db.connect()
        self.batch_id = int(datetime.now().strftime('%Y%m%d%H%M%S'))
        logger.info(f"Batch ID: {self.batch_id}")
        
    def extract_data(self, use_sample_data=True):
        """Extract data from source systems"""
        logger.info("=" * 60)
        logger.info("EXTRACT PHASE")
        logger.info("=" * 60)
        
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
        
        logger.info("Extract phase completed")
        for key, df in data.items():
            logger.info(f"  - {key}: {len(df)} records")
        
        return data
    
    def transform_data(self, data):
        """Transform and clean data"""
        logger.info("=" * 60)
        logger.info("TRANSFORM PHASE")
        logger.info("=" * 60)
        
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
                logger.info(f"  - Removed {before - after} duplicates from {key}")
        
        # Handle missing values
        logger.info("Handling missing values...")
        for key, df in data.items():
            null_counts = df.isnull().sum()
            if null_counts.any():
                logger.info(f"  - {key} null values:\n{null_counts[null_counts > 0]}")
        
        # Data type conversions
        logger.info("Converting data types...")
        data['transactions']['transaction_date'] = pd.to_datetime(
            data['transactions']['transaction_date']
        )
        
        logger.info("Transform phase completed")
        return data
    
    def load_dimensions(self, data):
        """Load all dimension tables"""
        logger.info("=" * 60)
        logger.info("LOAD DIMENSIONS")
        logger.info("=" * 60)
        
        # Load date dimension first
        self.dim_loader.load_date_dimension('2023-01-01', '2025-12-31')
        
        # Load other dimensions
        self.dim_loader.load_promotion_dimension(data['promotions'])
        self.dim_loader.load_store_dimension_scd1(data['stores'])
        self.dim_loader.load_customer_dimension_scd2(data['customers'])
        self.dim_loader.load_product_dimension_scd2(data['products'])
        
        logger.info("All dimensions loaded successfully")
    
    def load_facts(self, data):
        """Load fact tables"""
        logger.info("=" * 60)
        logger.info("LOAD FACTS")
        logger.info("=" * 60)
        
        # Load sales fact table
        rows_loaded = self.fact_loader.load_fact_sales(
            data['transactions'],
            batch_id=self.batch_id
        )
        
        # Build aggregates
        self.fact_loader.build_daily_aggregates()
        
        logger.info(f"Fact loading completed: {rows_loaded} rows")
    
    def generate_data_quality_report(self):
        """Generate data quality report"""
        logger.info("=" * 60)
        logger.info("DATA QUALITY REPORT")
        logger.info("=" * 60)
        
        queries = {
            'Total Customers': "SELECT COUNT(*) FROM dim_customer WHERE is_current = TRUE",
            'Total Products': "SELECT COUNT(*) FROM dim_product WHERE is_current = TRUE",
            'Total Stores': "SELECT COUNT(*) FROM dim_store",
            'Total Promotions': "SELECT COUNT(*) FROM dim_promotion",
            'Total Transactions': "SELECT COUNT(DISTINCT transaction_id) FROM fact_sales",
            'Total Sales Rows': "SELECT COUNT(*) FROM fact_sales",
            'Total Revenue': "SELECT ROUND(SUM(total_amount), 2) FROM fact_sales",
            'Total Profit': "SELECT ROUND(SUM(profit), 2) FROM fact_sales"
        }
        
        for metric, query in queries.items():
            result = self.db.execute_query(query).fetchone()[0]
            logger.info(f"  {metric}: {result}")
    
    def run_full_load(self, use_sample_data=True):
        """Run complete ETL pipeline"""
        try:
            start_time = datetime.now()
            logger.info("=" * 60)
            logger.info(f"ETL PIPELINE STARTED AT {start_time}")
            logger.info("=" * 60)
            
            # Initialize
            self.initialize()
            
            # Extract
            data = self.extract_data(use_sample_data)
            
            # Transform
            data = self.transform_data(data)
            
            # Load Dimensions
            self.load_dimensions(data)
            
            # Load Facts
            self.load_facts(data)
            
            # Quality Report
            self.generate_data_quality_report()
            
            # Complete
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info(f"ETL PIPELINE COMPLETED SUCCESSFULLY")
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"ETL Pipeline failed: {e}", exc_info=True)
            raise
        finally:
            self.db.close()
    
    def run_incremental_load(self, df_new_transactions):
        """Run incremental load for new transactions"""
        logger.info("Running incremental load...")
        
        try:
            self.initialize()
            
            # Transform new data
            data = {'transactions': df_new_transactions}
            data = self.transform_data(data)
            
            # Load facts only
            self.load_facts(data)
            
            logger.info("Incremental load completed")
            
        except Exception as e:
            logger.error(f"Incremental load failed: {e}")
            raise
        finally:
            self.db.close()

# Main execution
if __name__ == "__main__":
    pipeline = ETLPipeline()
    pipeline.run_full_load(use_sample_data=True)
```

### 5.7 Analytics and Reporting

```python
# analytics.py
"""
Analytics and reporting queries
"""
import pandas as pd
import logging
from db_connection import db_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Analytics:
    """Business intelligence and analytics queries"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.db.connect()
    
    def sales_by_month(self):
        """Monthly sales trend"""
        query = """
        SELECT 
            d.year,
            d.month,
            d.month_name,
            COUNT(DISTINCT f.transaction_id) as transactions,
            SUM(f.quantity) as units_sold,
            ROUND(SUM(f.profit), 2) as profit,
            ROUND(AVG(f.total_amount), 2) as avg_transaction_value
        FROM fact_sales f
        JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.year, d.month, d.month_name
        ORDER BY d.year, d.month
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Monthly sales analysis:")
        print(df.to_string(index=False))
        return df
    
    def top_products(self, limit=10):
        """Top selling products"""
        query = f"""
        SELECT 
            p.product_name,
            p.category,
            p.brand,
            SUM(f.quantity) as units_sold,
            ROUND(SUM(f.total_amount), 2) as revenue,
            ROUND(SUM(f.profit), 2) as profit
        FROM fact_sales f
        JOIN dim_product p ON f.product_key = p.product_key
        WHERE p.is_current = TRUE
        GROUP BY p.product_name, p.category, p.brand
        ORDER BY revenue DESC
        LIMIT {limit}
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info(f"Top {limit} products:")
        print(df.to_string(index=False))
        return df
    
    def customer_segments_analysis(self):
        """Customer segment performance"""
        query = """
        SELECT 
            c.customer_segment,
            COUNT(DISTINCT c.customer_id) as customer_count,
            COUNT(DISTINCT f.transaction_id) as transactions,
            ROUND(SUM(f.total_amount), 2) as revenue,
            ROUND(AVG(f.total_amount), 2) as avg_order_value,
            ROUND(SUM(f.total_amount) / COUNT(DISTINCT c.customer_id), 2) as revenue_per_customer
        FROM fact_sales f
        JOIN dim_customer c ON f.customer_key = c.customer_key
        WHERE c.is_current = TRUE
        GROUP BY c.customer_segment
        ORDER BY revenue DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Customer segment analysis:")
        print(df.to_string(index=False))
        return df
    
    def store_performance(self):
        """Store performance comparison"""
        query = """
        SELECT 
            s.store_name,
            s.store_type,
            s.city,
            s.state,
            COUNT(DISTINCT f.transaction_id) as transactions,
            SUM(f.quantity) as units_sold,
            ROUND(SUM(f.total_amount), 2) as revenue,
            ROUND(SUM(f.profit), 2) as profit,
            ROUND(SUM(f.profit) / SUM(f.total_amount) * 100, 2) as profit_margin_pct
        FROM fact_sales f
        JOIN dim_store s ON f.store_key = s.store_key
        GROUP BY s.store_name, s.store_type, s.city, s.state
        ORDER BY revenue DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Store performance:")
        print(df.to_string(index=False))
        return df
    
    def promotion_effectiveness(self):
        """Analyze promotion effectiveness"""
        query = """
        SELECT 
            p.promotion_name,
            p.promotion_type,
            p.discount_percentage,
            COUNT(DISTINCT f.transaction_id) as transactions,
            SUM(f.quantity) as units_sold,
            ROUND(SUM(f.total_amount), 2) as revenue,
            ROUND(SUM(f.discount_amount), 2) as total_discounts,
            ROUND(SUM(f.profit), 2) as profit
        FROM fact_sales f
        JOIN dim_promotion p ON f.promotion_key = p.promotion_key
        WHERE p.promotion_id != 'PROMO000'
        GROUP BY p.promotion_name, p.promotion_type, p.discount_percentage
        ORDER BY revenue DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Promotion effectiveness:")
        print(df.to_string(index=False))
        return df
    
    def weekly_sales_trend(self):
        """Weekly sales trends"""
        query = """
        SELECT 
            d.day_name,
            d.day_of_week,
            COUNT(DISTINCT f.transaction_id) as transactions,
            SUM(f.quantity) as units_sold,
            ROUND(SUM(f.total_amount), 2) as revenue,
            ROUND(AVG(f.total_amount), 2) as avg_transaction
        FROM fact_sales f
        JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.day_name, d.day_of_week
        ORDER BY d.day_of_week
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Weekly sales trend:")
        print(df.to_string(index=False))
        return df
    
    def category_performance(self):
        """Product category performance"""
        query = """
        SELECT 
            p.category,
            COUNT(DISTINCT p.product_id) as product_count,
            SUM(f.quantity) as units_sold,
            ROUND(SUM(f.total_amount), 2) as revenue,
            ROUND(SUM(f.profit), 2) as profit,
            ROUND(SUM(f.profit) / SUM(f.total_amount) * 100, 2) as profit_margin_pct
        FROM fact_sales f
        JOIN dim_product p ON f.product_key = p.product_key
        WHERE p.is_current = TRUE
        GROUP BY p.category
        ORDER BY revenue DESC
        """
        
        df = pd.read_sql(query, self.db.engine)
        logger.info("Category performance:")
        print(df.to_string(index=False))
        return df
    
    def run_all_reports(self):
        """Execute all analytics reports"""
        logger.info("=" * 60)
        logger.info("RUNNING ALL ANALYTICS REPORTS")
        logger.info("=" * 60)
        
        self.sales_by_month()
        print("\n")
        
        self.top_products()
        print("\n")
        
        self.customer_segments_analysis()
        print("\n")
        
        self.store_performance()
        print("\n")
        
        self.promotion_effectiveness()
        print("\n")
        
        self.weekly_sales_trend()
        print("\n")
        
        self.category_performance()
        
        logger.info("=" * 60)
        logger.info("ALL REPORTS COMPLETED")
        logger.info("=" * 60)

if __name__ == "__main__":
    analytics = Analytics(db_manager)
    analytics.run_all_reports()
```

---

## 6. USAGE GUIDE

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Update database configuration in config.py
```

### Running the Complete Pipeline

```bash
# 1. Generate sample data
python data_generator.py

# 2. Run full ETL pipeline
python etl_pipeline.py

# 3. Run analytics reports
python analytics.py
```

### Incremental Load Example

```python
from etl_pipeline import ETLPipeline
import pandas as pd

# Load new transactions
new_transactions = pd.read_csv('new_transactions.csv')

# Run incremental load
pipeline = ETLPipeline()
pipeline.run_incremental_load(new_transactions)
```

---

## 7. MONITORING AND MAINTENANCE

### ETL Monitoring Queries

```sql
-- Check ETL batch status
SELECT 
    etl_batch_id,
    COUNT(*) as records_loaded,
    MIN(etl_insert_date) as start_time,
    MAX(etl_insert_date) as end_time
FROM fact_sales
GROUP BY etl_batch_id
ORDER BY etl_batch_id DESC
LIMIT 10;

-- Check for dimension key errors
SELECT 
    COUNT(*) as orphaned_records
FROM fact_sales f
WHERE NOT EXISTS (
    SELECT 1 FROM dim_customer c 
    WHERE c.customer_key = f.customer_key
);

-- Monitor data freshness
SELECT 
    MAX(d.full_date) as latest_data_date,
    DATEDIFF(CURDATE(), MAX(d.full_date)) as days_old
FROM fact_sales f
JOIN dim_date d ON f.date_key = d.date_key;
```

---

## 8. BEST PRACTICES

### ETL Best Practices
1. **Idempotency**: Ensure ETL can be re-run without duplicating data
2. **Error Handling**: Comprehensive try-catch blocks and logging
3. **Incremental Loading**: Load only new/changed data when possible
4. **Data Quality**: Validate data before and after loading
5. **Performance**: Use bulk operations and appropriate indexes

### Data Warehouse Design Best Practices
1. **Slowly Changing Dimensions**: Choose appropriate SCD type
2. **Surrogate Keys**: Use integer surrogate keys for dimensions
3. **Grain Declaration**: Clearly define fact table grain
4. **Conformed Dimensions**: Reuse dimensions across fact tables
5. **Aggregate Tables**: Pre-calculate common aggregations

### Performance Optimization
1. **Partitioning**: Partition fact tables by date
2. **Indexing**: Create indexes on foreign keys and commonly queried columns
3. **Materialized Views**: For complex, frequently-run queries
4. **Statistics**: Keep database statistics up to date
5. **Vacuum/Analyze**: Regular maintenance operations

---

## 9. TROUBLESHOOTING

### Common Issues

**Issue**: Slow dimension lookups
- **Solution**: Ensure indexes exist on natural keys, use dimension caching

**Issue**: Duplicate records in fact table
- **Solution**: Add unique constraints on transaction_id + line_item_number

**Issue**: SCD Type 2 not updating correctly
- **Solution**: Verify effective_date and is_current logic

**Issue**: Memory errors during bulk loads
- **Solution**: Reduce batch_size in configuration

---

## 10. EXTENSION IDEAS

1. **Data Quality Framework**: Add data profiling and validation rules
2. **CDC Implementation**: Implement Change Data Capture for real-time updates
3. **Data Lineage**: Track data flow from source to target
4. **Audit Tables**: Log all ETL operations for compliance
5. **API Integration**: Add REST API for data warehouse access
6. **Visualization**: Integrate with Tableau/PowerBI
7. **Machine Learning**: Add predictive analytics capabilities
8. **Multi-tenancy**: Support multiple clients/organizations

---

## SUMMARY

This implementation provides:
- ✅ Complete conceptual, logical, and physical design
- ✅ Fully functional ETL pipeline with Python
- ✅ SCD Type 0, 1, and 2 implementations
- ✅ Sample data generation for testing
- ✅ Comprehensive error handling and logging
- ✅ Analytics and reporting capabilities
- ✅ Production-ready code structure

The entire solution is modular, scalable, and follows industry best practices for data warehouse development.(SUM(f.total_amount), 2) as revenue,
            ROUND