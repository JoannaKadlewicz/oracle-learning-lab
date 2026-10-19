-- Creates the learning schema tables. Run as ORASTUDY in ORAPDB1.
-- Target: Oracle Database 19c. DDL auto-commits.
-- Order: 01_create_tables.sql -> 02_seed_data.sql

CREATE TABLE departments (
    department_id    NUMBER(4)      CONSTRAINT departments_pk PRIMARY KEY,
    department_name  VARCHAR2(30)   CONSTRAINT departments_name_nn NOT NULL,
    location         VARCHAR2(30)
);

CREATE TABLE employees (
    employee_id      NUMBER(6)      CONSTRAINT employees_pk PRIMARY KEY,
    first_name       VARCHAR2(20),
    last_name        VARCHAR2(25)   CONSTRAINT employees_last_name_nn NOT NULL,
    email            VARCHAR2(50)   CONSTRAINT employees_email_uk UNIQUE,
    hire_date        DATE           CONSTRAINT employees_hire_date_nn NOT NULL,
    job_title        VARCHAR2(30),
    salary           NUMBER(8,2)    CONSTRAINT employees_salary_ck CHECK (salary > 0),
    commission_pct   NUMBER(3,2),
    manager_id       NUMBER(6)      CONSTRAINT employees_manager_fk REFERENCES employees (employee_id),
    department_id    NUMBER(4)      CONSTRAINT employees_department_fk REFERENCES departments (department_id)
);

CREATE TABLE customers (
    customer_id      NUMBER(6)      CONSTRAINT customers_pk PRIMARY KEY,
    customer_name    VARCHAR2(50)   CONSTRAINT customers_name_nn NOT NULL,
    country_code     CHAR(2),
    credit_limit     NUMBER(10,2)
);

CREATE TABLE products (
    product_id       NUMBER(6)      CONSTRAINT products_pk PRIMARY KEY,
    product_name     VARCHAR2(50)   CONSTRAINT products_name_nn NOT NULL,
    category         VARCHAR2(30),
    list_price       NUMBER(8,2)
);

CREATE TABLE orders (
    order_id         NUMBER(8)      CONSTRAINT orders_pk PRIMARY KEY,
    customer_id      NUMBER(6)      CONSTRAINT orders_customer_fk REFERENCES customers (customer_id),
    sales_rep_id     NUMBER(6)      CONSTRAINT orders_sales_rep_fk REFERENCES employees (employee_id),
    order_date       DATE           CONSTRAINT orders_order_date_nn NOT NULL,
    status           VARCHAR2(10)   CONSTRAINT orders_status_ck
                                        CHECK (status IN ('NEW', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_id         NUMBER(8)      CONSTRAINT order_items_order_fk
                                        REFERENCES orders (order_id) ON DELETE CASCADE,
    line_no          NUMBER(3),
    product_id       NUMBER(6)      CONSTRAINT order_items_product_fk REFERENCES products (product_id),
    quantity         NUMBER(5)      CONSTRAINT order_items_quantity_ck CHECK (quantity > 0),
    unit_price       NUMBER(8,2),
    CONSTRAINT order_items_pk PRIMARY KEY (order_id, line_no)
);

CREATE TABLE salary_grades (
    grade            CHAR(1)        CONSTRAINT salary_grades_pk PRIMARY KEY,
    min_salary       NUMBER(8,2)    CONSTRAINT salary_grades_min_nn NOT NULL,
    max_salary       NUMBER(8,2)    CONSTRAINT salary_grades_max_nn NOT NULL
);

-- Time zone and interval data (topic 14).
CREATE TABLE events (
    event_id         NUMBER(4)      CONSTRAINT events_pk PRIMARY KEY,
    event_name       VARCHAR2(40)   CONSTRAINT events_name_nn NOT NULL,
    starts_at        TIMESTAMP(0) WITH TIME ZONE,
    logged_at        TIMESTAMP(0) WITH LOCAL TIME ZONE,
    duration         INTERVAL DAY(2) TO SECOND(0),
    warranty         INTERVAL YEAR(2) TO MONTH
);

-- Intentionally left empty: aggregates and joins over a table with no rows.
CREATE TABLE promotions (
    promo_id         NUMBER(4)      CONSTRAINT promotions_pk PRIMARY KEY,
    promo_name       VARCHAR2(30),
    discount_pct     NUMBER(3)
);
