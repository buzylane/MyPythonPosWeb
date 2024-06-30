from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
import psycopg2
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Setup the directory for image uploads
UPLOAD_FOLDER = 'uploads/product_images'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)  # Create the directory if it does not exist
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/uploads/product_images/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Database connection parameters
DB_NAME = "BuzylaneMainDB"
DB_USER = "postgres"
DB_PASSWORD = "1qazxsw2"
DB_HOST = "localhost"
DB_PORT = "5432"

def connect_db():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Database connection failed: {e}")
        return None

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT userid, username, branch_id FROM users WHERE username = %s AND password = %s",
                           (username, password))
            user_record = cursor.fetchone()
            cursor.close()
            conn.close()
            if user_record:
                session['user_id'] = user_record[0]
                session['username'] = user_record[1]
                session['branch_id'] = user_record[2]  # Store branch ID in session
                logging.debug(f"User logged in: {user_record}")
                return redirect(url_for('dashboard'))
            else:
                flash("Incorrect username or password", "danger")
        else:
            flash("Failed to connect to the database", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/add_order', methods=['GET', 'POST'])
def add_order():
    conn = connect_db()
    if not conn:
        logging.error("Failed to connect to the database")
        flash("Failed to connect to the database", "danger")
        return render_template('error.html')  # Consider creating an error.html for better error handling

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT customerid, customername, phone FROM customers ORDER BY customername")
        customers = cursor.fetchall()
        cursor.execute("SELECT id, mode_name FROM pricing_mode ORDER BY mode_name")
        pricing_modes = cursor.fetchall()
        cursor.execute("SELECT sourceid, sourcename FROM ordersource ORDER BY sourcename")
        order_sources = cursor.fetchall()
        cursor.execute("SELECT serviceid, servicename FROM servicetype ORDER BY servicename")
        service_types = cursor.fetchall()
        cursor.execute("SELECT statusid, statusname FROM orderstatus ORDER BY statusid ASC")
        order_statuses = cursor.fetchall()
        cursor.execute("SELECT PaymentStatusID, PaymentStatusName FROM PaymentStatus ORDER BY PaymentStatusID ASC")
        payment_statuses = cursor.fetchall()
        cursor.execute("SELECT orderid FROM orders ORDER BY orderid ASC")
        order_ids = cursor.fetchall()

        logging.debug(f"Fetched order sources: {order_sources}")
        default_order_source = order_sources[0][0] if order_sources else None
        logging.debug(f"Default order source set to: {default_order_source}")

        if request.method == 'POST':
            customer_id = request.form.get('Customer_ID', '1')
            source = request.form.get('source', default_order_source)
            service = request.form.get('service_type', '0')
            total_amount = request.form.get('order_amount', '0.00')
            discount = request.form.get('total_discount', '0.00')
            status = request.form.get('order_status', default_order_status)
            payment_status = request.form.get('payment_status', default_payment_status)
            user_id = session.get('user_id')

            if order_id:
                query = """
                UPDATE orders SET 
                    customerid = %s, sourceid = %s, serviceid = %s, totalamount = %s, 
                    discount = %s, statusid = %s, paymentstatus = %s, userid = %s
                WHERE orderid = %s
                """
                params = (customer_id, source, service, total_amount, discount, status, payment_status, user_id, order_id)
                logging.debug(f"Updating order: {params}")
                cursor.execute(query, params)
            else:
                query = """
                INSERT INTO orders (customerid, sourceid, serviceid, totalamount, discount, statusid, paymentstatus, userid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING orderid
                """
                params = (customer_id, source, service, total_amount, discount, status, payment_status, user_id)
                logging.debug(f"Inserting new order: {params}")
                cursor.execute(query, params)
                order_id = cursor.fetchone()[0]

            conn.commit()
            flash('Order saved successfully!', 'success')
            return redirect(url_for('add_order', order_id=order_id))

        logging.debug(f"Rendering add_order template with order_sources: {order_sources}, default_order_source: {default_order_source}")
        return render_template('add_order.html',
                               customers=customers,
                               pricing_modes=pricing_modes,
                               order_sources=order_sources,
                               service_types=service_types,
                               order_statuses=order_statuses,
                               order_ids=order_ids,
                               payment_statuses=payment_statuses,
                               default_customer_name=default_customer_name,
                               default_customer_contact=default_customer_contact,
                               default_order_status=default_order_status,
                               default_payment_status=default_payment_status,
                               default_order_source=default_order_source)
    except Exception as e:
        logging.error(f"Error during database operation: {str(e)}")
        flash(f"Error during database operation: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

@app.route('/get_product_details', methods=['GET'])
def get_product_details():
    product_id = request.args.get('product_id')
    logging.debug(f"Fetching product details for product_id: {product_id}")
    if product_id:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT name, variant, retailprice, discount, quantity, promoprice, wholesaleprice, supplierprice, productcode, description, categoryid, subcategoryid, supplierid
                    FROM products
                    WHERE productid = %s
                """, (product_id,))
                product = cursor.fetchone()
                if product:
                    image_filename = f"{product_id}.jpg"
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if not os.path.isfile(image_path):
                        image_filename = "no_image.jpg"
                    web_path = url_for('uploaded_file', filename=image_filename)
                    return jsonify({
                        'product_id': product_id,
                        'name': product[0],
                        'variant': product[1],
                        'retailprice': product[2],
                        'discount': product[3],
                        'quantity': product[4],
                        'promoprice': product[5],
                        'wholesaleprice': product[6],
                        'supplierprice': product[7],
                        'productcode': product[8],
                        'description': product[9],
                        'categoryid': product[10],
                        'subcategoryid': product[11],
                        'supplierid': product[12],
                        'image_path': web_path
                    })
                else:
                    return jsonify({'error': 'Product not found'})
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
    return jsonify({'error': 'Invalid product id'})

@app.route('/get_product_details_by_code', methods=['GET'])
def get_product_details_by_code():
    product_code = request.args.get('product_code')
    logging.debug(f"Fetching product details for product_code: {product_code}")
    if product_code:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT productid, name, variant, retailprice, discount, quantity, promoprice, wholesaleprice, supplierprice, productcode, description, categoryid, subcategoryid, supplierid
                    FROM products
                    WHERE productcode = %s
                """, (product_code,))
                product = cursor.fetchone()
                if product:
                    image_filename = f"{product[0]}.jpg"
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if not os.path.isfile(image_path):
                        image_filename = "no_image.jpg"
                    web_path = url_for('uploaded_file', filename=image_filename)
                    return jsonify({
                        'product_id': product[0],
                        'name': product[1],
                        'variant': product[2],
                        'retailprice': product[3],
                        'discount': product[4],
                        'quantity': product[5],
                        'promoprice': product[6],
                        'wholesaleprice': product[7],
                        'supplierprice': product[8],
                        'productcode': product[9],
                        'description': product[10],
                        'categoryid': product[11],
                        'subcategoryid': product[12],
                        'supplierid': product[13],
                        'image_path': web_path
                    })
                else:
                    return jsonify({'error': 'Product not found'})
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
        else:
            return jsonify({'error': 'Database connection failed'})
    else:
        return jsonify({'error': 'Invalid product code'})

@app.route('/get_product_details_by_name', methods=['GET'])
def get_product_details_by_name():
    product_name = request.args.get('product_name')
    logging.debug(f"Fetching product details for product_name: {product_name}")
    if product_name:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT productid, retailprice, discount FROM products WHERE name = %s", (product_name,))
                product = cursor.fetchone()
                if product:
                    return jsonify({
                        'product_code': product[0],
                        'unit_price': product[1],
                        'discount': product[2]
                    })
                else:
                    return jsonify({'error': 'Product not found'})
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
    return jsonify({'error': 'Invalid product name'})

@app.route('/orders')
def orders():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.orderid,
                o.orderdate,
                os.sourcename,
                st.servicename,
                c.customername,
                c.phone AS customer_contact,
                o.totalamount,
                o.discount,
                (o.totalamount - o.discount) AS total,
                ost.statusname,
                o.paymentstatus,
                o.expecteddeliverydate,
                u.username
            FROM
                orders o
            JOIN
                customers c ON o.customerid = c.customerid
            JOIN
                ordersource os ON o.sourceid = os.sourceid
            JOIN
                servicetype st ON o.serviceid = st.serviceid
            JOIN
                orderstatus ost ON o.statusid = ost.statusid
            JOIN
                users u ON o.userid = u.userid
            ORDER BY o.orderid
        """)
        orders = cursor.fetchall()
        cursor.close()
        conn.close()
    else:
        orders = []
        flash("Failed to connect to the database", "danger")

    return render_template('orders.html', orders=orders)

@app.route('/receive_payment', methods=['POST'])
def receive_payment():
    if request.method == 'POST':
        payment_date = request.form['payment_date']
        amount = request.form['amount']
        payment_method = request.form['payment_method']
        transaction_id = request.form['transaction_id']
        order_id = request.form['order_id']

        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO payments (orderid, paymentdate, amount, paymentmethod, transactionid)
                    VALUES (%s, %s, %s, %s, %s)
                """, (order_id, payment_date, amount, payment_method, transaction_id))
                conn.commit()
                flash('Payment received successfully!', 'success')
            except Exception as e:
                conn.rollback()
                flash(f'Failed to receive payment: {e}', 'danger')
            finally:
                cursor.close()
                conn.close()
        else:
            flash("Failed to connect to the database", "danger")

    return redirect(url_for('add_order'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = connect_db()
    if conn:
        dashboard_data = fetch_dashboard_data(conn)
        conn.close()
    else:
        flash("Failed to connect to the database", "danger")
        dashboard_data = {}

    return render_template('dashboard.html', data=dashboard_data)

def fetch_dashboard_data(conn):
    data = {}
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM orders")
        data['order_count'] = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(totalamount) FROM orders")
        data['total_sales'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM customers")
        data['customer_count'] = cursor.fetchone()[0]

    except Exception as e:
        logging.error(f"Failed to fetch dashboard data: {e}")
        data = {}

    cursor.close()
    return data

@app.route('/revenue')
def revenue():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('revenue.html')

@app.route('/inventory')
def inventory():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('inventory.html')

@app.route('/expenditure')
def expenditure():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('expenditure.html')

@app.route('/hairstylists')
def hairstylists():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('hairstylists.html')

@app.route('/add_customer', methods=['POST'])
def add_customer():
    customername = request.form['customer_name']
    contact = request.form['contact']
    contact2 = request.form['contact2']
    email = request.form['email']
    location = request.form['location']

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO customers (customername, email, phone, phone2, location) VALUES (%s, %s, %s, %s, %s)",
                (customername, email, contact, contact2, location)
            )
            conn.commit()
            flash('Customer added successfully!', 'success')
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash('Email already exists.', 'danger')
        except Exception as e:
            conn.rollback()
            flash(f'Failed to add customer: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Failed to connect to the database. Please try again.', 'danger')

    return redirect(url_for('add_order'))

@app.route('/get_customer_contact', methods=['GET'])
def get_customer_contact():
    customer_name = request.args.get('customer_name')
    if customer_name:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT phone FROM customers WHERE customername = %s", (customer_name,))
                contact = cursor.fetchone()
                if contact:
                    return jsonify({'contact': contact[0]})
                else:
                    return jsonify({'contact': 'No contact found'})
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'contact': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
    return jsonify({'contact': 'Invalid customer name'})

@app.route('/order/<int:order_id>')
def order_detail(order_id):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.orderid,
                o.orderdate,
                os.sourcename,
                st.servicename,
                c.customername,
                c.phone AS customer_contact,
                o.totalamount,
                o.discount,
                (o.totalamount - o.discount) AS total,
                ost.statusname,
                o.paymentstatus,
                o.expecteddeliverydate,
                u.username
            FROM
                orders o
            JOIN
                customers c ON o.customerid = c.customerid
            JOIN
                ordersource os ON o.sourceid = os.sourceid
            JOIN
                servicetype st ON o.serviceid = st.serviceid
            JOIN
                orderstatus ost ON o.statusid = ost.statusid
            JOIN
                users u ON o.userid = u.userid
            WHERE
                o.orderid = %s
        """, (order_id,))
        order = cursor.fetchone()
        cursor.close()
        conn.close()
    else:
        order = None
        flash("Failed to connect to the database", "danger")

    return render_template('order_detail.html', order=order)

@app.route('/search_products', methods=['GET'])
def search_products():
    query = request.args.get('query')
    if query:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT DISTINCT productid, name, productcode
                    FROM products
                    WHERE CAST(productid AS TEXT) ILIKE %s OR LOWER(name) ILIKE %s
                """, (f"%{query.lower()}%", f"%{query.lower()}%"))
                products = cursor.fetchall()
                return jsonify(products)
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify([])
            finally:
                cursor.close()
                conn.close()
    return jsonify([])

@app.route('/search_products_inventory', methods=['GET'])
def search_products_inventory():
    query = request.args.get('query')
    if query:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT DISTINCT name
                    FROM products
                    WHERE LOWER(name) ILIKE %s
                """, (f"%{query.lower()}%",))
                products = cursor.fetchall()
                return jsonify([{'name': p[0]} for p in products])
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify([])
            finally:
                cursor.close()
                conn.close()
    return jsonify([])

@app.route('/get_variant_details', methods=['GET'])
def get_variant_details():
    product_name = request.args.get('product_name')
    variant = request.args.get('variant')

    if product_name and variant:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT productid, retailprice, discount FROM products WHERE name = %s AND variant = %s", (product_name, variant))
                variant_details = cursor.fetchone()
                if variant_details:
                    return jsonify({
                        'product_code': variant_details[0],
                        'unit_price': variant_details[1],
                        'discount': variant_details[2]
                    })
                else:
                    return jsonify({'error': 'Variant not found'})
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
    return jsonify({'error': 'Invalid parameters'})

@app.route('/get_variants', methods=['GET'])
def get_variants():
    product_name = request.args.get('product_name')
    if product_name:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT variant FROM products WHERE name = %s ORDER BY variant", (product_name,))
                variants = cursor.fetchall()
                return jsonify([variant[0] for variant in variants])
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify([])
            finally:
                cursor.close()
                conn.close()
    return jsonify([])

@app.route('/get_order_details')
def get_order_details():
    order_id = request.args.get('order_id')
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT o.orderid, o.orderdate, c.customername, c.phone, o.totalamount, o.discount,
                o.totalamount - o.discount AS total, os.sourcename, o.statusid, o.paymentstatus, 
                o.expecteddeliverydate, u.username
                FROM orders o
                JOIN customers c ON o.customerid = c.customerid
                JOIN users u ON o.userid = u.userid
                JOIN ordersource os ON o.sourceid = os.sourceid
                WHERE o.orderid = %s
            """, (order_id,))
            order = cursor.fetchone()
            if order:
                return jsonify({
                    'order_id': order[0],
                    'order_date': order[1],
                    'customer_name': order[2],
                    'customer_contact': order[3],
                    'total_amount': order[4],
                    'discount': order[5],
                    'total': order[6],
                    'source_name': order[7],
                    'status': order[8],
                    'payment_status': order[9],
                    'delivery_date': order[10],
                    'user': order[11]
                })
        except Exception as e:
            logging.error(f"Database query failed: {e}")
            return jsonify({'error': 'Query failed'})
        finally:
            cursor.close()
            conn.close()
    return jsonify({'error': 'Order not found'})

@app.route('/search_customers', methods=['GET'])
def search_customers():
    query = request.args.get('query')
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT customerid, customername, phone FROM customers WHERE customername ILIKE %s", ('%' + query + '%',))
            customers = cursor.fetchall()
            return jsonify([{'id': cust[0], 'name': cust[1], 'contact': cust[2]} for cust in customers])
        except Exception as e:
            logging.error(f"Database query failed: {e}")
            return jsonify([])
        finally:
            cursor.close()
            conn.close()
    return jsonify([])

@app.route('/get_orders', methods=['GET'])
def get_orders():
    conn = connect_db()
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                SELECT
                    o.orderid,
                    c.customername,
                    o.orderdate,
                    os.statusname,
                    o.totalamount
                FROM
                    orders o
                JOIN customers c ON o.customerid = c.customerid
                JOIN orderstatus os ON o.statusid = os.statusid
                ORDER BY o.orderid DESC LIMIT 100
            """
            cursor.execute(query)
            orders = cursor.fetchall()
            cursor.close()
            orders_list = []
            for order in orders:
                orders_list.append({
                    "order_id": order[0],
                    "customer_name": order[1],
                    "date": order[2].strftime('%Y-%m-%d'),
                    "status": order[3],
                    "total_amount": f"¢{order[4]:,.2f}",
                    "actions": f"<button class='btn btn-info' onclick='viewOrder({order[0]})'>View</button>"
                })
            return jsonify(orders_list)
        except Exception as e:
            logging.error(f"Database query failed: {e}")
            return jsonify([]), 500
        finally:
            conn.close()
    return jsonify([]), 500

@app.route('/get_order_product_details', methods=['GET'])
def get_order_product_details():
    order_id = request.args.get('order_id')
    if order_id:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT 
                        productid, variant, quantity, unitprice, discount, totalamount
                    FROM 
                        orderdetails
                    WHERE 
                        orderid = %s
                """, (order_id,))
                products = cursor.fetchall()
                return jsonify([{
                    'product_code': product[0],
                    'variant': product[1],
                    'quantity': product[2],
                    'unit_price': product[3],
                    'discount': product[4],
                    'total_amount': product[5]
                } for product in products])
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
    return jsonify({'error': 'Invalid order id'})

@app.route('/get_products', methods=['GET'])
def get_products():
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.productid, p.name, p.variant, p.quantity, p.retailprice, p.promoprice, p.wholesaleprice, p.supplierprice,
                   (p.retailprice - p.supplierprice) AS retailprofit,
                   (p.promoprice - p.supplierprice) AS promoprofit,
                   (p.wholesaleprice - p.supplierprice) AS wholesaleprofit,
                   sup.suppliername AS supplier,
                   cat.categoryname AS category,
                   subcat.subcategoryname AS subcategory
            FROM products p
            LEFT JOIN suppliers sup ON p.supplierid = sup.supplierid
            LEFT JOIN productcategory cat ON p.categoryid = cat.categoryid
            LEFT JOIN productsubcategory subcat ON p.subcategoryid = subcat.subcategoryid
            ORDER BY p.name
        """)
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([{
            'product_id': p[0],
            'name': p[1],
            'variant': p[2],
            'quantity': p[3],
            'retailprice': p[4],
            'promoprice': p[5],
            'wholesaleprice': p[6],
            'supplierprice': p[7],
            'retailprofit': p[8],
            'promoprofit': p[9],
            'wholesaleprofit': p[10],
            'supplier': p[11],
            'category': p[12],
            'subcategory': p[13],
            'image_path': f'/uploads/product_images/{p[0]}.jpg'
        } for p in products])
    return jsonify([])

@app.route('/edit_product', methods=['POST'])
def edit_product():
    if 'product_id' not in request.form:
        return jsonify({'status': 'error', 'message': 'Missing product ID'}), 400

    product_id = request.form['product_id']
    name = request.form.get('name')
    variant = request.form.get('variant')
    quantity = request.form.get('quantity')
    retailprice = request.form.get('retailPrice')
    promoprice = request.form.get('promoPrice')
    wholesaleprice = request.form.get('wholesalePrice')
    supplierprice = request.form.get('supplierPrice')
    categoryid = request.form.get('categoryId')
    subcategoryid = request.form.get('subcategoryId')
    supplierid = request.form.get('supplierId')
    productcode = request.form.get('productCode')
    description = request.form.get('description')

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE products 
                SET name = %s, variant = %s, quantity = %s, retailprice = %s, promoprice = %s,
                    wholesaleprice = %s, supplierprice = %s, categoryid = %s, subcategoryid = %s, 
                    supplierid = %s, productcode = %s, description = %s
                WHERE productid = %s
            """, (name, variant, quantity, retailprice, promoprice, wholesaleprice, supplierprice, categoryid, subcategoryid, supplierid, productcode, description, product_id))

            if 'image' in request.files:
                image = request.files['image']
                if image and allowed_file(image.filename):
                    extension = image.filename.rsplit('.', 1)[1].lower()
                    filename = f"{product_id}.{extension}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    image.save(save_path)
                else:
                    return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400

            conn.commit()
            return jsonify({'status': 'success'})

        except Exception as e:
            conn.rollback()
            return jsonify({'status': 'error', 'message': str(e)})
        finally:
            cursor.close()
            conn.close()
    return jsonify({'status': 'error', 'message': 'Failed to connect to database'})

@app.route('/add_product', methods=['POST'])
def add_product():
    conn = connect_db()
    if conn:
        data = request.form
        cursor = conn.cursor()
        try:
            if not data['name'] or not data['supplierId']:
                return jsonify({'status': 'error', 'message': 'Product name and supplier are required'}), 400

            def to_numeric(value):
                return float(value) if value else None

            product_code = data['productCode'] if data['productCode'] else None

            cursor.execute("""
                INSERT INTO products (name, variant, quantity, retailprice, promoprice, wholesaleprice, supplierprice, categoryid, subcategoryid, supplierid, productcode, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING productid
            """, (data['name'], data['variant'], to_numeric(data['quantity']), to_numeric(data['retailPrice']),
                  to_numeric(data['promoPrice']), to_numeric(data['wholesalePrice']), to_numeric(data['supplierPrice']),
                  data['categoryId'] if data['categoryId'] else None, data['subcategoryId'] if data['subcategoryId'] else None,
                  data['supplierId'], product_code, data['description']))
            product_id = cursor.fetchone()[0]
            conn.commit()

            if 'image' in request.files:
                image = request.files['image']
                if image and allowed_file(image.filename):
                    extension = image.filename.rsplit('.', 1)[1].lower()
                    filename = f"{product_id}.{extension}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    image.save(save_path)
                else:
                    return jsonify({'status': 'error', 'message': 'Invalid file type'}), 400

            return jsonify({'status': 'success', 'product_id': product_id})
        except Exception as e:
            logging.error(f"Error adding product: {e}")
            return jsonify({'status': 'error', 'message': str(e)})
        finally:
            cursor.close()
            conn.close()
    return jsonify({'status': 'error', 'message': 'Database connection failed'})

@app.route('/search_suppliers', methods=['GET'])
def search_suppliers():
    query = request.args.get('query')
    if query:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT supplierid, suppliername
                    FROM suppliers
                    WHERE LOWER(suppliername) ILIKE %s
                """, (f"%{query.lower()}%",))
                suppliers = cursor.fetchall()
                return jsonify([{
                    'supplierid': s[0],
                    'name': s[1]
                } for s in suppliers])
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify([])
            finally:
                cursor.close()
                conn.close()
    return jsonify([])

@app.route('/get_suppliers', methods=['GET'])
def get_suppliers():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT supplierid, suppliername FROM suppliers ORDER BY suppliername")
    suppliers = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'supplierid': s[0], 'name': s[1]} for s in suppliers])

@app.route('/get_product_variants', methods=['GET'])
def get_product_variants():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT variant from products ORDER BY variant ASC")
    variants = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'variant': v[0]} for v in variants])

@app.route('/get_product_variants_inventory', methods=['GET'])
def get_product_variants_inventory():
    query = request.args.get('query', '')

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT variant
        FROM products
        WHERE LOWER(variant) ILIKE %s
        ORDER BY variant ASC
    """, (f"%{query.lower()}%",))
    variants = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'variant': v[0]} for v in variants])

@app.route('/get_categories', methods=['GET'])
def get_categories():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT categoryid, categoryname FROM productcategory ORDER BY categoryname")
    categories = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'categoryid': c[0], 'name': c[1]} for c in categories])

@app.route('/get_subcategories', methods=['GET'])
def get_subcategories():
    category_id = request.args.get('category_id')

    if not category_id or not category_id.isdigit():
        return jsonify([])

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT subcategoryid, subcategoryname FROM productsubcategory WHERE categoryid = %s ORDER BY subcategoryname",
            (category_id,))
        subcategories = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify([{'subcategoryid': s[0], 'name': s[1]} for s in subcategories])

    return jsonify([])

@app.route('/get_subcategories2', methods=['GET'])
def get_subcategories2():
    category_id = request.args.get('category_id')
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT subcategoryid, subcategoryname, categoryid FROM productsubcategory ORDER BY subcategoryname", (category_id,))
    subcategories = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'subcategoryid': s[0], 'name': s[1], 'categoryid': s[2]} for s in subcategories])

@app.route('/get_sources')
def get_sources():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sourceid, sourcename FROM ordersource ORDER BY sourcename")
    sources = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'id': s[0], 'name': s[1]} for s in sources])

@app.route('/get_services')
def get_services():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT serviceid, servicename FROM servicetype ORDER BY servicename")
    services = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'id': s[0], 'name': s[1]} for s in services])

@app.route('/get_customers')
def get_customers():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT customerid, customername FROM customers ORDER BY customername")
    customers = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'id': c[0], 'name': c[1]} for c in customers])

@app.route('/get_statuses')
def get_statuses():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT statusid, statusname FROM orderstatus ORDER BY statusname")
    statuses = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'id': s[0], 'name': s[1]} for s in statuses])

@app.route('/get_payment_statuses')
def get_payment_statuses():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT PaymentStatusID, PaymentStatusName FROM PaymentStatus ORDER BY PaymentStatusName")
    payment_statuses = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'id': s[0], 'name': s[1]} for s in payment_statuses])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    CORS(app)
