-- -----------------------------------------------------
-- Table northwind.customers
-- -----------------------------------------------------

use catalog mysandbox;
use dl_northwind;
CREATE TABLE IF NOT EXISTS dl_northwind.customer_region1
(
id	INT,
company	STRING,
last_name	STRING,
first_name	STRING,
email_address	STRING,
job_title	STRING,
business_phone	STRING,
home_phone	STRING,
mobile_phone	STRING,
fax_number	STRING,
address	STRING,
city	STRING,
state_province	STRING,
zip_postal_code	STRING,
country_region	STRING,
web_page	STRING,
notes	STRING,
attachments	STRING
);

CREATE TABLE IF NOT EXISTS dl_northwind.customer_region2
(
id	INT,
company	STRING,
last_name	STRING,
first_name	STRING,
email_address	STRING,
job_title	STRING,
business_phone	STRING,
home_phone	STRING,
mobile_phone	STRING,
fax_number	STRING,
address	STRING,
city	STRING,
state_province	STRING,
zip_postal_code	STRING,
country_region	STRING,
web_page	STRING,
notes	STRING,
attachments	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.employees
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.employees
(
id	INT,
company	STRING,
last_name	STRING,
first_name	STRING,
email_address	STRING,
job_title	STRING,
business_phone	STRING,
home_phone	STRING,
mobile_phone	STRING,
fax_number	STRING,
address	STRING,
city	STRING,
state_province	STRING,
zip_postal_code	STRING,
country_region	STRING,
web_page	STRING,
notes	STRING,
attachments	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.privileges
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.privileges
(
id INT,
privilege_name	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.employee_privileges
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.employee_privileges
(
employee_id	INT,
privilege_id	INT
)
;
-- -----------------------------------------------------
-- Table northwind.inventory_transaction_types
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.inventory_transaction_types
(
id	INT,
type_name	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.shippers
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.shippers
(
id	INT,
company	STRING,
last_name	STRING,
first_name	STRING,
email_address	STRING,
job_title	STRING,
business_phone	STRING,
home_phone	STRING,
mobile_phone	STRING,
fax_number	STRING,
address	STRING,
city	STRING,
state_province	STRING,
zip_postal_code	STRING,
country_region	STRING,
web_page	STRING,
notes	STRING,
attachments	STRING
)
;


CREATE TABLE IF NOT EXISTS dl_northwind.shippers2
(
id	INT,
company	STRING,
last_name	STRING,
first_name	STRING,
email_address	STRING,
job_title	STRING,
business_phone	STRING,
home_phone	STRING,
mobile_phone	STRING,
fax_number	STRING,
address	STRING,
city	STRING,
state_province	STRING,
zip_postal_code	STRING,
country_region	STRING,
web_page	STRING,
notes	STRING,
attachments	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.orders_tax_status
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS dl_northwind.orders_tax_status
(
id	INT,
tax_status_name	STRING
)
;

-- -----------------------------------------------------
-- Table northwind.orders_status
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.orders_status
(
id	INT,
status_name	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.orders
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.orders
(
id	INT,
employee_id	INT,
customer_id	INT,
order_date	TIMESTAMP,
shipped_date	TIMESTAMP,
shipper_id	INT,
ship_name	STRING,
ship_address	STRING,
ship_city	STRING,
ship_state_province	STRING,
ship_zip_postal_code	STRING,
ship_country_region	STRING,
shipping_fee	FLOAT,
taxes	FLOAT,
payment_type	STRING,
paid_date	TIMESTAMP,
notes	STRING,
tax_rate	FLOAT,
tax_status_id	INT,
status_id	INT
)
;
-- -----------------------------------------------------
-- Table northwind.products
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.products
(
supplier_ids	STRING,
id	INT,
product_code	STRING,
product_name	STRING,
description	STRING,
standard_cost	FLOAT,
list_price	FLOAT,
reorder_level	INT,
target_level	INT,
quantity_per_unit	STRING,
discontinued	INT,
minimum_reorder_quantity	INT,
category	STRING,
attachments	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.purchase_order_status
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.purchase_order_status
(
id	INT,
status	STRING
)
;

-- -----------------------------------------------------
-- Table northwind.suppliers
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS dl_northwind.suppliers
(
id	INT,
company	STRING,
last_name	STRING,
first_name	STRING,
email_address	STRING,
job_title	STRING,
business_phone	STRING,
home_phone	STRING,
mobile_phone	STRING,
fax_number	STRING,
address	STRING,
city	STRING,
state_province	STRING,
zip_postal_code	STRING,
country_region	STRING,
web_page	STRING,
notes	STRING,
attachments	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.purchase_orders
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.purchase_orders
(
id	INT,
supplier_id	INT,
created_by	INT,
submitted_date	TIMESTAMP,
creation_date	TIMESTAMP,
status_id	INT,
expected_date	TIMESTAMP,
shipping_fee	FLOAT,
taxes	FLOAT,
payment_date	TIMESTAMP,
payment_amount	FLOAT,
payment_method	STRING,
notes	STRING,
approved_by	INT,
approved_date	TIMESTAMP,
submitted_by	INT
)
;
-- -----------------------------------------------------
-- Table northwind.inventory_transactions
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS dl_northwind.inventory_transactions
(
id	INT,
transaction_type	INT,
transaction_created_date	TIMESTAMP,
transaction_modified_date	TIMESTAMP,
product_id	INT,
quantity	INT,
purchase_order_id	INT,
customer_order_id	INT,
comments	STRING
)
;

-- -----------------------------------------------------
-- Table northwind.invoices
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS dl_northwind.invoices
(
id	INT,
order_id	INT,
invoice_date	TIMESTAMP,
due_date	TIMESTAMP,
tax	FLOAT,
shipping	FLOAT,
amount_due	FLOAT
)
;
-- -----------------------------------------------------
-- Table northwind.order_details_status
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.order_details_status
(
id	INT,
status	STRING
)
;
-- -----------------------------------------------------
-- Table northwind.order_details
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.order_details
(
id	INT,
order_id	INT,
product_id	INT,
quantity	FLOAT,
unit_price	FLOAT,
discount	FLOAT,
status_id	INT,
date_allocated	TIMESTAMP,
purchase_order_id	INT,
inventory_id	INT
)
;
-- -----------------------------------------------------
-- Table northwind.purchase_order_details
-- -----------------------------------------------------

CREATE TABLE IF NOT EXISTS dl_northwind.purchase_order_details
(
id	INT,
purchase_order_id	INT,
product_id	INT,
quantity	FLOAT,
unit_cost	FLOAT,
date_received	TIMESTAMP,
posted_to_inventory	INT,
inventory_id	INT
)
;


-- -----------------------------------------------------
-- Table northwind.sales_reports
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS dl_northwind.sales_reports 
(
  group_by STRING,
  display STRING,
  title STRING,
  filter_row_source STRING,
  default STRING
)
;



CREATE TABLE IF NOT EXISTS dl_northwind.strings
(
string_id INT,
string_data STRING
)
;


