-- Loads a small deterministic dataset. Run as ORASTUDY after 01_create_tables.sql.
-- Target: Oracle Database 19c. Ends with an explicit COMMIT.
--
-- Edge cases built into the data:
--   - Department 40 (Research) has no employees              -> outer joins, NOT EXISTS
--   - Employee 108 has no department (department_id NULL)    -> outer joins, NOT IN pitfalls
--   - Employee 100 has no manager (manager_id NULL)          -> self-join, hierarchy root
--   - commission_pct is NULL for most employees              -> NVL, AVG/COUNT with NULLs
--   - Salary ties: 104/105 (6000), 106/107 (4800)            -> RANK vs DENSE_RANK, WITH TIES
--   - Customer 4 has no orders; customer 5 has NULL country  -> anti-joins, NULL grouping
--   - Product 14 never sold; product 15 has NULL list_price  -> outer joins, NULL arithmetic
--   - Order 1006 is on a month boundary at 23:30             -> DATE time component, TRUNC
--   - Order 1007 has a NULL sales_rep_id                     -> join cardinality
--   - Event 1 is in Warsaw just before the DST switch         -> time zone regions vs offsets
--   - Event 2 is on 29 February with a 1-year warranty        -> INTERVAL arithmetic errors
--   - Event 4 has NULL timestamps and intervals               -> NULLs in datetime functions
--   - Table promotions has no rows                            -> COUNT/SUM/MAX on an empty table

INSERT INTO departments (department_id, department_name, location) VALUES (10, 'Administration', 'Seattle');
INSERT INTO departments (department_id, department_name, location) VALUES (20, 'Sales', 'London');
INSERT INTO departments (department_id, department_name, location) VALUES (30, 'IT', 'Warsaw');
INSERT INTO departments (department_id, department_name, location) VALUES (40, 'Research', NULL);

INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (100, 'Steven', 'King', 'SKING', DATE '2015-06-17', 'President', 24000, NULL, NULL, 10);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (101, 'Neena', 'Kochhar', 'NKOCHHAR', DATE '2016-09-21', 'Sales Manager', 14000, 0.30, 100, 20);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (102, 'Lex', 'De Haan', 'LDEHAAN', DATE '2017-01-13', 'IT Manager', 12000, NULL, 100, 30);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (103, 'Alexander', 'Hunold', 'AHUNOLD', DATE '2018-01-03', 'Programmer', 9000, NULL, 102, 30);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (104, 'Bruce', 'Ernst', 'BERNST', DATE '2019-05-21', 'Programmer', 6000, NULL, 102, 30);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (105, 'John', 'Russell', 'JRUSSELL', DATE '2019-10-01', 'Sales Rep', 6000, 0.20, 101, 20);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (106, 'Karen', 'Partners', 'KPARTNER', DATE '2020-01-05', 'Sales Rep', 4800, 0.15, 101, 20);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (107, 'Diana', 'Lorentz', 'DLORENTZ', DATE '2020-02-07', 'Programmer', 4800, NULL, 102, 30);
INSERT INTO employees (employee_id, first_name, last_name, email, hire_date, job_title, salary, commission_pct, manager_id, department_id)
VALUES (108, 'Kimberely', 'Grant', NULL, DATE '2021-05-24', 'Sales Rep', 3500, 0.15, 101, NULL);

INSERT INTO customers (customer_id, customer_name, country_code, credit_limit) VALUES (1, 'Acme Corp', 'US', 5000);
INSERT INTO customers (customer_id, customer_name, country_code, credit_limit) VALUES (2, 'Globex', 'GB', 3000);
INSERT INTO customers (customer_id, customer_name, country_code, credit_limit) VALUES (3, 'Initech', 'US', NULL);
INSERT INTO customers (customer_id, customer_name, country_code, credit_limit) VALUES (4, 'Umbrella', 'PL', 2000);
INSERT INTO customers (customer_id, customer_name, country_code, credit_limit) VALUES (5, 'Hooli', NULL, 1000);

INSERT INTO products (product_id, product_name, category, list_price) VALUES (11, 'Laptop', 'Hardware', 1200);
INSERT INTO products (product_id, product_name, category, list_price) VALUES (12, 'Mouse', 'Hardware', 25);
INSERT INTO products (product_id, product_name, category, list_price) VALUES (13, 'Office Suite', 'Software', 300);
INSERT INTO products (product_id, product_name, category, list_price) VALUES (14, 'Antivirus', 'Software', 50);
INSERT INTO products (product_id, product_name, category, list_price) VALUES (15, 'Consulting Hour', 'Services', NULL);

INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1001, 1, 105, DATE '2024-01-15', 'SHIPPED');
INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1002, 1, 106, DATE '2024-02-03', 'SHIPPED');
INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1003, 2, 105, DATE '2024-02-20', 'CANCELLED');
INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1004, 3, 108, DATE '2024-03-01', 'NEW');
INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1005, 5, 106, DATE '2024-03-15', 'SHIPPED');
INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1006, 2, 105, TO_DATE('2024-03-31 23:30:00', 'YYYY-MM-DD HH24:MI:SS'), 'NEW');
INSERT INTO orders (order_id, customer_id, sales_rep_id, order_date, status) VALUES (1007, 1, NULL, DATE '2024-04-02', 'NEW');

INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1001, 1, 11, 2, 1150);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1001, 2, 12, 5, 25);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1002, 1, 13, 10, 280);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1003, 1, 11, 1, 1200);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1004, 1, 12, 20, 22);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1004, 2, 15, 8, 150);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1005, 1, 13, 3, 300);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1006, 1, 11, 1, 1100);
INSERT INTO order_items (order_id, line_no, product_id, quantity, unit_price) VALUES (1006, 2, 12, 1, 25);
-- Order 1007 intentionally has no items.

INSERT INTO salary_grades (grade, min_salary, max_salary) VALUES ('A', 1000, 4999.99);
INSERT INTO salary_grades (grade, min_salary, max_salary) VALUES ('B', 5000, 9999.99);
INSERT INTO salary_grades (grade, min_salary, max_salary) VALUES ('C', 10000, 19999.99);
INSERT INTO salary_grades (grade, min_salary, max_salary) VALUES ('D', 20000, 49999.99);

INSERT INTO events (event_id, event_name, starts_at, logged_at, duration, warranty)
VALUES (1, 'Launch webinar', TIMESTAMP '2024-03-31 01:30:00 Europe/Warsaw', TIMESTAMP '2024-03-31 01:30:00 Europe/Warsaw',
        INTERVAL '0 01:30:00' DAY TO SECOND, NULL);
INSERT INTO events (event_id, event_name, starts_at, logged_at, duration, warranty)
VALUES (2, 'Leap day release', TIMESTAMP '2024-02-29 09:00:00 +00:00', TIMESTAMP '2024-02-29 09:00:00 +00:00',
        INTERVAL '1 00:00:00' DAY TO SECOND, INTERVAL '1-0' YEAR TO MONTH);
INSERT INTO events (event_id, event_name, starts_at, logged_at, duration, warranty)
VALUES (3, 'Quarter close', TIMESTAMP '2024-03-31 23:30:00 America/New_York', TIMESTAMP '2024-03-31 23:30:00 America/New_York',
        INTERVAL '0 00:45:00' DAY TO SECOND, INTERVAL '0-6' YEAR TO MONTH);
INSERT INTO events (event_id, event_name, starts_at, logged_at, duration, warranty)
VALUES (4, 'Retrospective', NULL, NULL, NULL, NULL);

-- promotions intentionally has no rows.

COMMIT;
