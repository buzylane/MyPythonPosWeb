from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory, make_response
import psycopg2
import requests
from flask_cors import CORS
import os
from flask import session, flash, make_response

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm, mm
from reportlab.graphics.barcode import code128
import io
from datetime import datetime, timedelta
import logging
import smtplib
from email.mime.text import MIMEText


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads/product_images'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/uploads/product_images/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
#
# # Database connection parameters
# DB_NAME = "BuzylaneMainDB"
# DB_USER = "postgres"
# DB_PASSWORD = "1qazxsw2"
# DB_HOST = "localhost"
# DB_PORT = "5432"
#

# DB_NAME = "awsdb"
# DB_USER = "postgres"
# DB_PASSWORD = "1qazxsw2"
# DB_HOST = "localhost"
# DB_PORT = "5432"
#

DB_NAME = "awsdb"
DB_USER = "postgres"
DB_PASSWORD = "1qazxsw2"
DB_HOST = "buzylaneawsdb.cdu6akewglav.eu-north-1.rds.amazonaws.com"
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

# Set the timeout period (e.g., 30 minutes)
SESSION_TIMEOUT = timedelta(minutes=30)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            # Retrieve user information along with the business ID
            cursor.execute("""
                SELECT u.userid, u.username, u.branch_id, u.role_id, b.business_id, b.business_name
                FROM users u
                JOIN branch br ON u.branch_id = br.branch_id
                JOIN business b ON br.business_id = b.business_id
                WHERE u.username = %s AND u.password = %s
            """, (username, password))
            user_record = cursor.fetchone()
            if user_record:
                session['user_id'] = user_record[0]
                session['username'] = user_record[1]
                session['branch_id'] = user_record[2]
                session['role_id'] = user_record[3]
                session['business_id'] = user_record[4]
                session['business_name'] = user_record[5]

                # Record session start
                cursor.execute("""
                    INSERT INTO sessionmanagement (userid, session_start, is_active)
                    VALUES (%s, %s, %s)
                """, (user_record[0], datetime.now(), True))
                conn.commit()

                logging.debug(f"User logged in: {user_record}")
                cursor.close()
                conn.close()
                session['last_active'] = datetime.now()
                return redirect(url_for('dashboard'))
            else:
                cursor.close()
                conn.close()
                flash("Incorrect username or password", "danger")
        else:
            flash("Failed to connect to the database", "danger")
    return render_template('login.html')


@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    conn = connect_db()
    if conn and user_id:
        cursor = conn.cursor()
        # Record session end
        cursor.execute("""
            UPDATE sessionmanagement
            SET session_end = %s, is_active = %s
            WHERE userid = %s AND is_active = %s
        """, (datetime.now(), False, user_id, True))
        conn.commit()
        cursor.close()
        conn.close()

    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('branch_id', None)
    session.pop('role_id', None)
    session.pop('business_id', None)
    session.pop('business_name', None)
    return redirect(url_for('login'))


@app.before_request
def check_session_timeout():
    if 'user_id' in session:
        last_active = session.get('last_active')
        now = datetime.now()

        if last_active:
            if isinstance(last_active, str):
                last_active = datetime.fromisoformat(last_active)
            else:
                last_active = datetime.now()  # Fallback if not a string

            if now - last_active > SESSION_TIMEOUT:
                flash('Your session has ended due to inactivity. Please login', 'warning')
                return logout()

        session['last_active'] = now.isoformat()  # Update last active time


@app.route('/add_order', methods=['GET', 'POST'])
def add_order():
    conn = connect_db()
    if not conn:
        logging.error("Failed to connect to the database")
        flash("Failed to connect to the database", "danger")
        return render_template('error.html')

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT customerid, customername, phone FROM customers ORDER BY customername")
        customers = cursor.fetchall()
        cursor.execute("SELECT id, mode_name FROM pricing_mode ORDER BY id")
        pricing_modes = cursor.fetchall()
        cursor.execute("SELECT sourceid, sourcename FROM ordersource ORDER BY sourceid")
        order_sources = cursor.fetchall()
        cursor.execute("SELECT serviceid, servicename FROM servicetype ORDER BY serviceid")
        service_types = cursor.fetchall()
        cursor.execute("SELECT statusid, statusname FROM orderstatus ORDER BY statusid ASC")
        order_statuses = cursor.fetchall()
        cursor.execute("SELECT PaymentStatusID, PaymentStatusName FROM PaymentStatus ORDER BY PaymentStatusID ASC")
        payment_statuses = cursor.fetchall()
        cursor.execute("SELECT branch_id, branch_name FROM branch ORDER BY branch_id")
        branches = cursor.fetchall()

        order_id = request.args.get('order_id')
        if order_id:
            cursor.execute("""
                            SELECT o.receiving_branch_id, r.branch_name 
                            FROM orders o 
                            JOIN branch r ON o.receiving_branch_id = r.branch_id 
                            WHERE o.orderid = %s
                        """, (order_id,))
            receiving_branch = cursor.fetchone()
            if receiving_branch:
                receiving_branch_id = receiving_branch[0]
        else:
            receiving_branch_id = None

        default_order_source = order_sources[0][0] if order_sources else None

        cursor.execute("SELECT PaymentStatusID FROM PaymentStatus ORDER BY PaymentStatusID ASC LIMIT 1")
        default_payment_status = cursor.fetchone()[0] if cursor.rowcount > 0 else None

        cursor.execute("SELECT id FROM pricing_mode ORDER BY id ASC LIMIT 1")
        default_pricing_mode = pricing_modes[0][0] if pricing_modes else None

        role_id = session.get('role_id')
        branch_id = session.get('branch_id')

        if request.method == 'POST':
            order_id = request.form.get('order_id')
            customer_id = request.form.get('Customer_ID', '1')

            if not customer_id:
                customer_id = '1'
            source = request.form.get('source', default_order_source)
            service = request.form.get('service_type', '1')
            total_amount = request.form.get('order_amount', '0.00')
            discount = request.form.get('total_discount', '0.00')
            status = request.form.get('order_status', '1')
            payment_status = request.form.get('payment_status', '1')
            user_id = session.get('user_id')
            pricing_mode = '1'
            receiving_branch_id = request.form.get('receiving_branch_id', branch_id)

            if role_id != 1:
                branch_id = session.get('branch_id')
            else:
                branch_id = request.form.get('branch_id', branch_id)

            if order_id:
                query = """
                UPDATE orders
                SET customerid = %s, sourceid = %s, serviceid = %s, totalamount = %s, discount = %s, statusid = %s, paymentstatus = %s, userid = %s, branch_id = %s, receiving_branch_id = %s
                WHERE orderid = %s
                """
                params = (customer_id, source, service, total_amount, discount, status, payment_status, user_id, branch_id, receiving_branch_id, order_id)
                cursor.execute(query, params)
                notification_message = f"Order {order_id} has been updated."
            else:
                query = """
                INSERT INTO orders (customerid, sourceid, serviceid, totalamount, discount, statusid, paymentstatus, userid, branch_id, receiving_branch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING orderid
                """
                params = (customer_id, source, service, total_amount, discount, status, payment_status, user_id, branch_id, receiving_branch_id)
                cursor.execute(query, params)
                order_id = cursor.fetchone()[0]
                notification_message = f"New order {order_id} has been placed."

            products = request.form.getlist('Product_Code[]')
            quantities = request.form.getlist('Quantity[]')
            unit_prices = request.form.getlist('Unit_Price[]')
            discounts = request.form.getlist('discount[]')
            total_amounts = request.form.getlist('Total_Amount[]')
            variants = request.form.getlist('Variant[]')

            cursor.execute("DELETE FROM orderdetails WHERE orderid = %s", (order_id,))
            for i in range(len(products)):
                product_code = products[i]
                quantity = quantities[i]
                unit_price = unit_prices[i]
                discount = discounts[i]
                total_amount = total_amounts[i]
                variant = variants[i]

                if not product_code or not quantity or not unit_price or not discount or not total_amount:
                    flash('Missing product details. Please ensure all product fields are filled.', 'danger')
                    return redirect(url_for('add_order', order_id=order_id))

                order_details_query = """
                INSERT INTO orderdetails (orderid, productid, variant, quantity, unitprice, discount)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                order_details_params = (order_id, product_code, variant, quantity, unit_price, discount)
                cursor.execute(order_details_query, order_details_params)

            conn.commit()

            cursor.execute("SELECT userid FROM users WHERE role_id = 1")
            admin_users = cursor.fetchall()
            for admin_user in admin_users:
                add_notification(admin_user[0], notification_message)

            cursor.close()
            return redirect(url_for('add_order', order_id=order_id))

        order_details = None
        payments = []
        if order_id:
            cursor.execute("SELECT * FROM orders WHERE orderid = %s", (order_id,))
            order_details = cursor.fetchone()

            cursor.execute("""
                SELECT paymentdate, amount, paymentmethod, reference_id
                FROM payments
                WHERE orderid = %s
                ORDER BY paymentdate DESC
            """, (order_id,))
            payments = cursor.fetchall()

        return render_template('add_order.html',
                               default_payment_status=default_payment_status,
                               customers=customers,
                               order_details=order_details,
                               order_sources=order_sources,
                               pricing_modes=pricing_modes,
                               service_types=service_types,
                               order_statuses=order_statuses,
                               payment_statuses=payment_statuses,
                               default_order_source=default_order_source,
                               payments=payments,
                               branches=branches,
                               role_id=role_id,
                               branch_id=branch_id)
    except Exception as e:
        logging.error(f"Error during database operation: {str(e)}")
        flash(f"Error during database operation: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('add_order'))


@app.route('/get_product_details_by_code', methods=['GET'])
def get_product_details_by_code():
    product_code = request.args.get('product_code')
    pricing_mode = request.args.get('pricing_mode', type=int)
    logging.debug(f"Fetching product details for product_code: {product_code} with pricing_mode: {pricing_mode}")
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
                    unit_price = product[3]  # Default to retailprice
                    if pricing_mode == 2:
                        unit_price = product[6]  # Use promoprice
                    elif pricing_mode == 3:
                        unit_price = product[7]  # Use wholesaleprice

                    image_filename = f"{product[0]}.jpg"
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if not os.path.isfile(image_path):
                        image_filename = "no_image.jpg"
                    web_path = url_for('uploaded_file', filename=image_filename)
                    return jsonify({
                        'product_id': product[0],
                        'name': product[1],
                        'variant': product[2],
                        'unit_price': unit_price,
                        'discount': product[4],
                        'quantity': product[5],
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
    pricing_mode = request.args.get('pricing_mode', type=int)
    logging.debug(f"Fetching product details for product_name: {product_name}, pricing_mode: {pricing_mode}")

    if product_name and pricing_mode in [1, 2, 3, 4]:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                query = "SELECT productid, retailprice, discount FROM products WHERE name = %s"

                if pricing_mode == 2:
                    query = "SELECT productid, promoprice, discount FROM products WHERE name = %s"
                elif pricing_mode == 3:
                    query = "SELECT productid, wholesaleprice, discount FROM products WHERE name = %s"
                elif pricing_mode == 4:
                    query = "SELECT productid, distributerprice, discount FROM products WHERE name = %s"

                cursor.execute(query, (product_name,))
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
    return jsonify({'error': 'Invalid product name or pricing mode'})


@app.route('/orders')
def orders():
    if 'username' not in session:
        return redirect(url_for('login'))

    business_id = session.get('business_id')
    if not business_id:
        flash("Business ID not found in session", "danger")
        return redirect(url_for('login'))

    conn = connect_db()
    orders = []
    orders_today = []

    if conn:
        cursor = conn.cursor()

        # Fetch all orders related to the business
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
                ps.paymentstatusname,
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
            JOIN
                paymentstatus ps ON o.paymentstatus = ps.paymentstatusid
            JOIN
                branch b ON u.branch_id = b.branch_id
            WHERE
                b.business_id = %s
            ORDER BY o.orderid DESC
        """, (business_id,))
        orders = cursor.fetchall()

        # Fetch today's orders related to the business
        today_date = datetime.today().strftime('%Y-%m-%d')
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
                ps.paymentstatusname,
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
            JOIN
                paymentstatus ps ON o.paymentstatus = ps.paymentstatusid
            JOIN
                branch b ON u.branch_id = b.branch_id
            WHERE
                o.expecteddeliverydate = %s AND b.business_id = %s
            ORDER BY o.orderid DESC
        """, (today_date, business_id))
        orders_today = cursor.fetchall()

        cursor.close()
        conn.close()
    else:
        flash("Failed to connect to the database", "danger")

    return render_template('orders.html', orders=orders, orders_today=orders_today)




@app.route('/receive_payment', methods=['POST'])
def receive_payment():
    order_id = request.form['order_id']
    payment_date = request.form['payment_date']
    amount = request.form['amount']
    payment_method = request.form['payment_method']
    transaction_id = request.form['transaction_id']
    payment_status = 'Completed'

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO payments (orderid, paymentdate, amount, paymentmethod, reference_id, payment_status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (order_id, payment_date, amount, payment_method, transaction_id, payment_status))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)})
        finally:
            cursor.close()
            conn.close()
    else:
        return jsonify({'success': False, 'message': 'Failed to connect to the database'})


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
    business_id = session.get('business_id')  # Retrieve business_id from session

    conn = connect_db()
    if not conn:
        flash('Failed to connect to the database. Please try again.', 'danger')
        return redirect(url_for('add_order'))

    try:
        cursor = conn.cursor()
        # Insert the new customer into the database
        cursor.execute(
            "INSERT INTO customers (customername, email, phone, phone2, location, business_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (customername, email, contact, contact2, location, business_id)
        )
        conn.commit()
        flash('Customer added successfully!', 'success')

        # Send SMS after adding the customer and log the SMS in the sms_logs table
        welcome_message = f"Welcome to our store, {customername}! Thank you for registering."
        send_sms(contact, welcome_message)

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        flash('Email already exists.', 'danger')
    except Exception as e:
        conn.rollback()
        flash(f'Failed to add customer: {e}', 'danger')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('add_order'))


def send_sms(phone_number, message):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        user_id = session.get('user_id')
        if not user_id:
            raise Exception("No user logged in.")

        # Fetch SMS API credentials for the logged-in user
        cursor.execute("SELECT api_key, base_url, name FROM api_credentials WHERE userid = %s", (user_id,))
        creds = cursor.fetchone()

        if creds:
            url = creds[1]
            params = {
                "action": "send-sms",
                "api_key": creds[0],
                "to": phone_number,
                "from": creds[2],  # Use the 'name' from the database
                "sms": message
            }

            response = requests.get(url, params=params)
            response.raise_for_status()  # Raises an HTTPError for bad responses

            # Log the successful sending of the SMS
            cursor.execute("INSERT INTO sms_logs (phone_number, message, status, response, user_id) VALUES (%s, %s, %s, %s, %s)",
                           (phone_number, message, 'Success', response.text, user_id))

        else:
            raise Exception("SMS API credentials not found.")

    except requests.exceptions.RequestException as e:
        # Log any request exceptions
        cursor.execute("INSERT INTO sms_logs (phone_number, message, status, response, user_id) VALUES (%s, %s, %s, %s, %s)",
                       (phone_number, message, 'Failed', str(e), user_id))
    except Exception as e:
        print(f"Failed to send SMS:", e)
        print(user_id)
    finally:
        conn.commit()
        cursor.close()
        conn.close()


def add_api_credentials(name, api_key, base_url, user_id):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO api_credentials (name, api_key, base_url, userid) VALUES (%s, %s, %s, %s)",
                           (name, api_key, base_url, user_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Failed to add API credentials: {e}")
        finally:
            cursor.close()
            conn.close()



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
    business_id = session.get('business_id')

    if not business_id:
        return jsonify({'error': 'Business ID not found in session'}), 400

    if query:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT DISTINCT productid, name, productcode
                    FROM products
                    WHERE business_id = %s AND (CAST(productid AS TEXT) ILIKE %s OR LOWER(name) ILIKE %s)
                """, (business_id, f"%{query.lower()}%", f"%{query.lower()}%"))
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
    pricing_mode = request.args.get('pricing_mode', type=int)
    print(pricing_mode)
    if product_name and variant:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT productid, retailprice, discount, promoprice, wholesaleprice, distributerprice FROM products WHERE name = %s AND variant = %s", (product_name, variant))
                variant_details = cursor.fetchone()
                if variant_details:
                    unit_price = variant_details[1]  # Default to retailprice
                    if pricing_mode == 2:
                        unit_price = variant_details[3]  # Use promoprice
                    elif pricing_mode == 3:
                        unit_price = variant_details[4]  # Use wholesaleprice
                    elif pricing_mode == 4:
                        unit_price = variant_details[5]  # Use distributerprice

                    return jsonify({
                        'product_code': variant_details[0],
                        'unit_price': unit_price,
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


@app.route('/add_payment', methods=['POST'])
def add_payment():
    payment_date = request.form.get('payment_date')
    amount = request.form.get('amount')
    payment_method_id = request.form.get('payment_method_id')
    transaction_id = request.form.get('transaction_id')
    order_id = request.form.get('order_id')

    # Validate required fields
    if not all([payment_date, amount, payment_method_id, transaction_id, order_id]):
        return jsonify(success=False, error="Missing required fields")

    # Check for valid data types
    try:
        amount = float(amount)  # Convert amount to float
        payment_date = datetime.strptime(payment_date, '%Y-%m-%d')  # Validate date
    except ValueError as e:
        logging.error(f"Data type error: {e}")
        return jsonify(success=False, error="Invalid input format")

    conn = connect_db()
    if not conn:
        return jsonify(success=False, error="Database connection failed")

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO payments (orderid, paymentdate, amount, paymentmethod, reference_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (order_id, payment_date, amount, payment_method_id, transaction_id))
        conn.commit()
        return jsonify(success=True)
    except Exception as e:
        logging.error(f"Database error while inserting payment: {e}")
        return jsonify(success=False, error="Database error")
    finally:
        cursor.close()
        conn.close()

    return jsonify(success=False, error="Unhandled error")


@app.route('/get_order_details')
def get_order_details():
    order_id = request.args.get('order_id')
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT o.orderid, o.orderdate, c.customername, c.phone, o.totalamount, o.discount,
                o.totalamount - o.discount AS total, os.sourceid, os.sourcename, o.statusid, o.paymentstatus, 
                o.expecteddeliverydate, u.username, c.customerid, se.serviceid, se.servicename, pm.id, pm.mode_name,
                b.branch_id, b.branch_name, r.branch_id, r.branch_name
                FROM orders o
                JOIN customers c ON o.customerid = c.customerid
                JOIN users u ON o.userid = u.userid
                JOIN ordersource os ON o.sourceid = os.sourceid
                JOIN servicetype se ON se.serviceid = o.serviceid
                JOIN pricing_mode pm ON o.pricing_mode_id = pm.id
                JOIN branch b ON o.branch_id = b.branch_id
                JOIN branch r ON o.receiving_branch_id = r.branch_id
                WHERE o.orderid = %s
            """, (order_id,))
            order = cursor.fetchone()

            cursor.execute("""
                SELECT od.productid, p.name, od.variant, od.quantity, od.unitprice, od.discount, od.totalamount
                FROM orderdetails od
                JOIN products p ON od.productid = p.productid
                WHERE od.orderid = %s
            """, (order_id,))
            products = cursor.fetchall()

            if order:
                # Include current user's branch ID from the session
                current_user_branch_id = session.get('branch_id')

                return jsonify({
                    'order_id': order[0],
                    'order_date': order[1],
                    'customer_name': order[2],
                    'customer_contact': order[3],
                    'total_amount': order[4],
                    'discount': order[5],
                    'total': order[6],
                    'source_id': order[7],
                    'source_name': order[8],
                    'status': order[9],
                    'payment_status': order[10],
                    'delivery_date': order[11],
                    'user': order[12],
                    'customer_id': order[13],
                    'service_id': order[14],
                    'service': order[15],
                    'pricing_mode_id': order[16],
                    'pricing_mode_name': order[17],
                    'branch_id': order[18],
                    'branch_name': order[19],
                    'receiving_branch_id': order[20],
                    'receiving_branch_name': order[21],
                    'currentUserBranchId': current_user_branch_id,
                    'products': [
                        {
                            'product_code': product[0],
                            'product_name': product[1],
                            'variant': product[2],
                            'quantity': product[3],
                            'unit_price': product[4],
                            'discount': product[5],
                            'total_amount': product[6]
                        } for product in products
                    ]
                })
            else:
                logging.error('Order not found')
                return jsonify({'error': 'Order not found'})
        except Exception as e:
            logging.error(f"Database query failed: {e}")
            return jsonify({'error': 'Query failed'})
        finally:
            cursor.close()
            conn.close()
    else:
        return jsonify({'error': 'Failed to connect to the database'})




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
    business_id = session.get('business_id')  # Retrieve business_id from session
    branch_id = session.get('branch_id')  # Retrieve branch_id from session

    if not business_id or not branch_id:
        return jsonify({'error': 'Business ID or Branch ID not found in session'}), 400

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
            SELECT DISTINCT p.productid, p.name, p.variant, 
                   total_stk.total_quantity,  -- Sum of quantities across all branches
                   p.retailprice, p.promoprice, p.wholesaleprice, p.supplierprice,
                   (p.retailprice - p.supplierprice) AS retailprofit,
                   (p.promoprice - p.supplierprice) AS promoprofit,
                   (p.wholesaleprice - p.supplierprice) AS wholesaleprofit,
                   sup.suppliername AS supplier,
                   cat.categoryname AS category,
                   subcat.subcategoryname AS subcategory,
                   COALESCE(stk.quantity, 0) AS branch_qty  -- Quantity at the specific branch
            FROM products p
            LEFT JOIN suppliers sup ON p.supplierid = sup.supplierid
            LEFT JOIN productcategory cat ON p.categoryid = cat.categoryid
            LEFT JOIN productsubcategory subcat ON p.subcategoryid = subcat.subcategoryid
            LEFT JOIN (
                SELECT product_id, SUM(quantity) AS total_quantity
                FROM stock
                GROUP BY product_id
            ) total_stk ON p.productid = total_stk.product_id
            LEFT JOIN stock stk ON p.productid = stk.product_id AND stk.branch_id = %s
            WHERE p.business_id = %s
            ORDER BY p.name
            """, (branch_id, business_id))
            products = cursor.fetchall()
            product_list = [{
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
                'branch_qty': p[14],
                'image_path': f'/uploads/product_images/{p[0]}.jpg'
            } for p in products]
            return jsonify(product_list)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()
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
            business_id = session.get('business_id')

            cursor.execute("""
                INSERT INTO products (name, variant, quantity, retailprice, promoprice, wholesaleprice, supplierprice, categoryid, subcategoryid, supplierid, productcode, description, business_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING productid
            """, (data['name'], data['variant'], to_numeric(data['quantity']), to_numeric(data['retailPrice']),
                  to_numeric(data['promoPrice']), to_numeric(data['wholesalePrice']), to_numeric(data['supplierPrice']),
                  data['categoryId'] if data['categoryId'] else None, data['subcategoryId'] if data['subcategoryId'] else None,
                  data['supplierId'], product_code, data['description'], business_id))
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

# @app.route('/get_payment_methods', methods=['GET'])
# def get_payment_methods():
#     conn = connect_db()
#     if conn:
#         cursor = conn.cursor()
#         cursor.execute("SELECT method_id, method_name FROM payment_methods ORDER BY method_id ASC")
#         payment_methods = cursor.fetchall()
#         cursor.close()
#         conn.close()
#         return jsonify({'payment_methods': [{'id': pm[0], 'name': pm[1]} for pm in payment_methods]})
#     else:
#         return jsonify({'error': 'Failed to connect to the database'}), 500

@app.route('/delete_payment', methods=['POST'])
def delete_payment():
    payment_id = request.form.get('paymentId')
    if not payment_id:
        return jsonify(success=False, message="No payment ID provided."), 400

    try:
        payment_id = int(payment_id)
        conn = connect_db()
        if conn is None:
            return jsonify(success=False, message="Failed to connect to the database."), 500

        cursor = conn.cursor()
        cursor.execute("DELETE FROM payments WHERE paymentid = %s", (payment_id,))
        conn.commit()
        if cursor.rowcount > 0:
            return jsonify(success=True, message="Payment deleted successfully.")
        else:
            return jsonify(success=False, message="Payment not found."), 404
    except ValueError:
        return jsonify(success=False, message="Invalid payment ID format."), 400
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        if conn:
            cursor.close()
            conn.close()


@app.route('/save_delivery_info', methods=['POST'])
def save_delivery_info():
    data = request.json
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            sql_command = """
                INSERT INTO deliveries (orderid, delivery_address, expected_delivery_date, actual_delivery_date, delivery_status, courier_name, tracking_number, notes, delivery_contact_name, delivery_contact_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (orderid) DO UPDATE SET
                    delivery_address = EXCLUDED.delivery_address,
                    expected_delivery_date = EXCLUDED.expected_delivery_date,
                    actual_delivery_date = EXCLUDED.actual_delivery_date,
                    delivery_status = EXCLUDED.delivery_status,
                    courier_name = EXCLUDED.courier_name,
                    tracking_number = EXCLUDED.tracking_number,
                    notes = EXCLUDED.notes,
                    delivery_contact_name = EXCLUDED.delivery_contact_name,
                    delivery_contact_number = EXCLUDED.delivery_contact_number;
            """
            cur.execute(sql_command, (
                data['orderId'],
                data['deliveryAddress'],
                data['expectedDeliveryDate'],
                data.get('actualDeliveryDate'),  # handle None if not provided
                data['deliveryStatus'],
                data['courierName'],
                data['trackingNumber'],
                data['notes'],
                data['contactName'],
                data['contactNumber']
            ))
            conn.commit()

            # Verify entry
            cur.execute("SELECT * FROM deliveries WHERE orderid = %s", (data['orderId'],))
            entry = cur.fetchone()


            return jsonify(success=True, data=entry)
    except Exception as e:
        conn.rollback()
        print("Error during database operation:", str(e))  # Log the error
        return jsonify(success=False, error=str(e))
    finally:
        if conn:
            conn.close()


@app.route('/get_delivery_info', methods=['GET'])
def get_delivery_info():
    order_id = request.args.get('order_id')
    if not order_id:
        return jsonify(success=False, error="No order ID provided"), 400

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT delivery_address, expected_delivery_date, actual_delivery_date, delivery_status,
                       courier_name, tracking_number, notes, delivery_contact_name, delivery_contact_number
                FROM deliveries WHERE orderid = %s
            """, (order_id,))
            delivery_info = cur.fetchone()

            if delivery_info:
                delivery_data = {
                    'deliveryAddress': delivery_info[0],
                    'expectedDeliveryDate': delivery_info[1].strftime('%Y-%m-%d') if delivery_info[1] else None,
                    'actualDeliveryDate': delivery_info[2].strftime('%Y-%m-%d') if delivery_info[2] else None,
                    'deliveryStatus': delivery_info[3],
                    'courierName': delivery_info[4],
                    'trackingNumber': delivery_info[5],
                    'notes': delivery_info[6],
                    'contactName': delivery_info[7],
                    'contactNumber': delivery_info[8]
                }

                return jsonify(success=True, deliveryInfo=delivery_data)
            else:
                # Return default values if no data found
                return jsonify(success=True, deliveryInfo=None)
    except Exception as e:
        return jsonify(success=False, error=str(e))
    finally:
        conn.close()


@app.route('/get_payment_methods', methods=['GET'])
def get_payment_methods():
    payment_methods = [
        {"method_id": "Cash", "method_name": "Cash"},
        {"method_id": "Momo", "method_name": "Momo"},
        {"method_id": "Telecel Cash", "method_name": "Telecel Cash"},
        {"method_id": "Airtel Tigo Cash", "method_name": "Airtel Tigo Cash"},
        {"method_id": "Bank", "method_name": "Bank"},
        {"method_id": "Other", "method_name": "Other"},
        # Add other payment methods as needed
    ]
    return jsonify(payment_methods)


@app.route('/get_order_payments/<int:order_id>', methods=['GET'])
def get_order_payments(order_id):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.paymentdate, p.amount, p.paymentmethod, p.reference_id, p.paymentid
            FROM payments p
            WHERE p.orderid = %s
            ORDER BY p.paymentdate DESC
        """, (order_id,))
        payments = cursor.fetchall()

        cursor.execute("SELECT totalamount FROM orders WHERE orderid = %s", (order_id,))
        order_amount = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return jsonify({
            'payments': [{'paymentdate': p[0].strftime('%Y-%m-%d'), 'amount': p[1], 'paymentmethod': p[2], 'transaction_id': p[3], 'paymentid': p[4]} for p in payments],
            'order_amount': order_amount
        })
    else:
        return jsonify({'error': 'Failed to connect to the database'}), 500


@app.route('/get_payment_statuses')
def get_payment_statuses():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT PaymentStatusID, PaymentStatusName FROM PaymentStatus ORDER BY PaymentStatusName")
    payment_statuses = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'id': s[0], 'name': s[1]} for s in payment_statuses])


@app.route('/search_customers', methods=['GET'])
def search_customers():
    query = request.args.get('query', '').strip().lower()
    if query:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT 
                        customerid AS id, 
                        customername AS name, 
                        phone AS contact, 
                        NULL AS branch_id, 
                        NULL AS branch_name, 
                        NULL AS branch_contact 
                    FROM 
                        customers 
                    WHERE 
                        LOWER(customername) LIKE %s

                    UNION

                    SELECT 
                        branch_id AS id, 
                        branch_name AS name, 
                        branch_contact AS contact, 
                        branch_id, 
                        branch_name, 
                        branch_contact 
                    FROM 
                        branch 
                    WHERE 
                        LOWER(branch_name) LIKE %s;
                """, (f"%{query}%", f"%{query}%"))

                results = cursor.fetchall()
                data = []
                for result in results:
                    item = {
                        'id': result[0],
                        'name': result[1],
                        'contact': result[2],
                        'branch_id': result[3] if result[3] else None,
                        'branch_name': result[4] if result[4] else None,
                        'branch_contact': result[5] if result[5] else None
                    }
                    data.append(item)

                return jsonify(data)
            except Exception as e:
                logging.error(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'}), 500
            finally:
                cursor.close()
                conn.close()
        else:
            return jsonify({'error': 'Database connection failed'}), 500
    return jsonify([])



@app.route('/generate_invoice/<int:order_id>')
def generate_invoice(order_id):
    logging.debug(f"Accessed route for order ID: {order_id}")
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            # Fetch order details
            cursor.execute("""
                SELECT o.orderid, o.orderdate, c.customername, c.phone, o.totalamount, o.discount,
                o.totalamount - o.discount AS total, os.sourcename, o.statusid, o.paymentstatus,
                o.expecteddeliverydate, u.username, c.customerid
                FROM orders o
                JOIN customers c ON o.customerid = c.customerid
                JOIN users u ON o.userid = u.userid
                JOIN ordersource os ON o.sourceid = os.sourceid
                WHERE o.orderid = %s
            """, (order_id,))
            order_details = cursor.fetchone()

            # Fetch product details associated with the order
            cursor.execute("""
                SELECT p.name, od.variant, od.quantity, od.unitprice, od.discount, od.totalamount
                FROM orderdetails od
                JOIN products p ON od.productid = p.productid
                WHERE od.orderid = %s
            """, (order_id,))
            product_details = cursor.fetchall()

            if not order_details:
                flash('Order not found.', 'danger')
                return redirect(url_for('orders'))

            # Generate PDF
            pdf_buffer = create_invoice_pdf(order_details, product_details)
            response = make_response(pdf_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=invoice_{order_id}.pdf'
            return response

        except Exception as e:
            logging.error(f"Database query failed: {e}")
            flash('Failed to generate invoice.', 'danger')
            return redirect(url_for('orders'))
        finally:
            cursor.close()
            conn.close()
    else:
        flash('Failed to connect to the database.', 'danger')
        return redirect(url_for('orders'))


from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors

def create_invoice_pdf(order_details, product_details):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # Dimensions of A4 paper

    # Constants for layout
    margin = 2*cm
    top_section_height = 3*cm
    bottom_section_height = 4*cm

    # Top header
    p.setStrokeColor(colors.black)
    p.setFillColor(colors.HexColor('#D32F2F'))  # Deep red color
    p.rect(0, height - top_section_height, width, top_section_height, fill=True)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width / 2, height - top_section_height + 1.5*cm, "INVOICE")

    # Invoice information
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 12)
    p.drawString(margin, height - top_section_height - 0.5*cm, f"Invoice to: {order_details[2]}")
    p.drawString(width - 4*cm, height - top_section_height - 0.5*cm, f"Date: {order_details[1].strftime('%Y-%m-%d')}")

    # Table Headers
    p.setStrokeColor(colors.black)
    p.setFillColor(colors.HexColor('#F2F2F2'))  # Light grey for table header background
    p.rect(margin, height - top_section_height - 2.5*cm, width - 2*margin, 1*cm, fill=True)
    p.setFillColor(colors.black)
    p.drawString(margin + 1*cm, height - top_section_height - 2*cm, "Item Description")
    p.drawString(width - 9*cm, height - top_section_height - 2*cm, "Price")
    p.drawString(width - 6*cm, height - top_section_height - 2*cm, "Qty.")
    p.drawString(width - 3*cm, height - top_section_height - 2*cm, "Total")

    # List of products
    y = height - top_section_height - 3.5*cm
    p.setFont("Helvetica", 10)
    for product in product_details:
        p.drawString(margin + 1*cm, y, product[0])
        p.drawString(width - 9*cm, y, f"${product[3]:,.2f}")
        p.drawString(width - 6*cm, y, str(product[2]))
        p.drawString(width - 3*cm, y, f"${product[3]*product[2]:,.2f}")
        y -= 0.5*cm

    # Footer section
    p.setFillColor(colors.HexColor('#D32F2F'))
    p.rect(0, 0, width, bottom_section_height, fill=True)
    p.setFillColor(colors.white)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(margin, 1*cm, "Thank you for your business")
    p.drawString(width - 7*cm, 1*cm, f"Total: ${order_details[6]:,.2f}")

    # Close the PDF and return the buffer
    p.showPage()
    p.save()
    buffer.seek(0)

    return buffer


@app.route('/print_receipt/<int:order_id>')
def print_receipt(order_id):
    # Your database query here to get order details and product details
    order_details = {}  # Simulated order details
    product_details = []  # Simulated product details

    # Create PDF for thermal printer
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=(220, 1000))  # Width 220 points (about 80mm) and sufficiently long
    p.setFont("Helvetica", 10)  # Small font size for thermal printers

    # Add text at positions that fit within 80mm width
    p.drawString(10, 980, f"Order ID: {order_id}")
    p.drawString(10, 960, "Details here...")

    # More details and formatting as needed
    y = 940
    for product in product_details:
        p.drawString(10, y, f"{product['name']} x {product['quantity']}")
        y -= 20

    p.showPage()
    p.save()
    buffer.seek(0)

    # Serve the PDF to be printed
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'inline; filename=receipt.pdf'
    return response


@app.route('/finalize_order', methods=['POST'])
def finalize_order():
    order_id = request.json.get('orderId')
    order_source = request.json.get('source')
    initiating_branch_id = request.json.get('branchId')  # Initiating branch ID from the form request
    receiving_branch_id = request.json.get('receivingbranchId')  # Receiving branch ID from the form request

    # Debug prints
    print(f"Order Source: {order_source}, Type: {type(order_source)}")
    print(f"Order ID: {order_id}")
    print(f"Initiating Branch ID: {initiating_branch_id}")
    print(f"Receiving Branch ID: {receiving_branch_id}")

    if not order_id:
        return jsonify(success=False, message="Order ID is missing."), 400

    if not initiating_branch_id or not receiving_branch_id:
        return jsonify(success=False, message="Branch IDs are missing."), 400

    conn = connect_db()
    try:
        cursor = conn.cursor()

        # If order_source is 5, bypass preceding functions and execute specific logic
        if str(order_source) == '5':  # Ensure order_source is compared as a string
            print("Order source is 5, executing specific logic...")

            try:
                # Fetch the products related to this order
                cursor.execute("""
                    SELECT od.productid, p.name, od.variant, od.quantity
                    FROM orderdetails od
                    JOIN products p ON od.productid = p.productid
                    WHERE od.orderid = %s
                """, (order_id,))
                products = cursor.fetchall()
                print(f"Fetched products: {products}")

                if not products:
                    print("No products found for this order.")
                    return jsonify(success=False, message="No products found for this order."), 400

                # Insert stock transactions for both initiating and receiving branches
                for product in products:
                    product_id, product_name, variant, quantity = product
                    print(f"Processing product {product_id} with quantity {quantity}")

                    # Fetch current quantity for initiating branch
                    cursor.execute("SELECT quantity FROM stock WHERE product_id = %s AND branch_id = %s", (product_id, initiating_branch_id))
                    result_initiating = cursor.fetchone()
                    current_quantity_initiating = result_initiating[0] if result_initiating else 0
                    print(f"Current quantity in initiating branch: {current_quantity_initiating}")
                    new_quantity_initiating = current_quantity_initiating - quantity

                    if new_quantity_initiating < 0:
                        print(f"Not enough stock in initiating branch for product {product_id}.")
                        return jsonify(success=False, message=f"Not enough stock in initiating branch for product {product_id}."), 400

                    # Record transfer out for initiating branch
                    cursor.execute("""
                        INSERT INTO stock_transactions (product_id, branch_id, quantity_changed, new_quantity, transaction_type, orderid)
                        VALUES (%s, %s, %s, %s, 'Transfer Out', %s)
                    """, (product_id, initiating_branch_id, -quantity, new_quantity_initiating, order_id))

                    # Fetch current quantity for receiving branch
                    cursor.execute("SELECT quantity FROM stock WHERE product_id = %s AND branch_id = %s", (product_id, receiving_branch_id))
                    result_receiving = cursor.fetchone()
                    current_quantity_receiving = result_receiving[0] if result_receiving else 0
                    print(f"Current quantity in receiving branch: {current_quantity_receiving}")
                    new_quantity_receiving = current_quantity_receiving + quantity

                    # Record transfer in for receiving branch
                    cursor.execute("""
                        INSERT INTO stock_transactions (product_id, branch_id, quantity_changed, new_quantity, transaction_type, orderid)
                        VALUES (%s, %s, %s, %s, 'Transfer In', %s)
                    """, (product_id, receiving_branch_id, quantity, new_quantity_receiving, order_id))

                # Update order status
                cursor.execute("""
                    UPDATE orders
                    SET statusid = %s, paymentstatus = %s
                    WHERE orderid = %s
                """, ('5', '2', order_id))

                conn.commit()
                print("Stock transactions and order update committed successfully.")
                return jsonify(success=True, message="Stock Received successfully.")
            except Exception as e:
                conn.rollback()
                print(f"Exception in specific logic for source 5: {str(e)}")
                return jsonify(success=False, message=f"Error in specific logic for source 5: {str(e)}"), 400
        else:
            # Proceed with the regular flow if order_source is not 5
            print("Order source is not 5, executing regular flow...")

            if not is_order_complete(order_id, conn):
                return jsonify(success=False, message="Order details are incomplete."), 400

            inventory_available, insufficient_products = is_inventory_available(order_id, conn, initiating_branch_id)
            if not inventory_available:
                product_details = ', '.join([f"{pname} (-{pvariant}) - Required: {rq}, Available: {aq}"
                                             for pname, pvariant, rq, aq in insufficient_products])
                return jsonify(success=False, message=f"Insufficient inventory for the following products: {product_details}"), 400

            if not is_payment_sufficient(order_id, conn):
                return jsonify(success=False, message="Insufficient payment."), 400

            products = fetch_order_products(order_id, conn)
            if not products:
                return jsonify(success=False, message="No products found for this order."), 400

            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE orders
                    SET statusid = %s, paymentstatus = %s
                    WHERE orderid = %s
                """, ('5', '2', order_id))

                # Update inventory for each product in the order using stock transactions
                for product_id, product_name, variant, quantity_sold in products:
                    # Fetch the current quantity for the initiating branch
                    cur.execute("SELECT quantity FROM stock WHERE product_id = %s and branch_id = %s", (product_id, initiating_branch_id))
                    current_quantity = cur.fetchone()[0]
                    new_quantity = current_quantity - quantity_sold

                    # Record the transaction for initiating branch
                    cur.execute("""
                        INSERT INTO stock_transactions (product_id, quantity_changed, new_quantity, transaction_type, branch_id, transaction_date, notes, orderid)
                        VALUES (%s, %s, %s, 'Outflow', %s, CURRENT_TIMESTAMP, 'Sale', %s)
                    """, (product_id, -quantity_sold, new_quantity, initiating_branch_id, order_id))

                conn.commit()
                return jsonify(success=True, message="Order has been finalized successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Exception: {str(e)}")
        return jsonify(success=False, message=str(e))
    finally:
        if conn:
            conn.close()







def fetch_order_products(order_id, conn):
    """ Fetch the product IDs, names, and quantities from the order details along with product details. """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT od.productid, p.name,p.variant, od.quantity
            FROM orderdetails od
            JOIN products p ON od.productid = p.productid
            WHERE od.orderid = %s
        """, (order_id,))
        return cur.fetchall()



def is_order_complete(order_id, conn):
    try:
        with conn.cursor() as cur:
            query = """
                SELECT EXISTS (
                    SELECT 1 FROM orders
                    WHERE orderid = %s AND
                          sourceid IS NOT NULL AND
                          serviceid IS NOT NULL AND
                          customerid IS NOT NULL AND  -- Assuming customerid should be checked
                          paymentstatus IS NOT NULL AND
                          statusid IS NOT NULL AND
                          totalamount IS NOT NULL AND
                          discount IS NOT NULL
                )
            """
            print(f"Executing SQL for order completeness check with order_id: {order_id}")
            cur.execute(query, (order_id,))
            result = cur.fetchone()
            if result is None:
                print("No result returned from the database.")
                return False
            print(f"Result of completeness check: {result}")
            return result[0]  # Returns True if the order is complete, False otherwise pricing_mode_id IS NOT NULL AND
    except Exception as e:
        print(f"Error checking order completeness: {str(e)}")
        return False


def is_payment_sufficient(order_id, conn):
    try:
        with conn.cursor() as cur:
            # Fetch total payments for the order
            cur.execute("""
                SELECT SUM(amount) FROM payments WHERE orderid = %s
            """, (order_id,))
            total_paid = cur.fetchone()[0] or 0  # Use 0 if fetchone() returns None

            # Fetch the total order amount
            cur.execute("""
                SELECT SUM(totalamount) FROM orderdetails WHERE orderid = %s
            """, (order_id,))
            total_order_amount = cur.fetchone()[0]

            # Check if payments cover the order amount
            return total_paid >= total_order_amount
    except Exception as e:
        print(f"Error checking payment sufficiency: {str(e)}")
        return False


def is_inventory_available(order_id, conn, branch_id):
    """
    Check if the inventory is available for the given order ID and branch ID.

    Parameters:
    order_id (int): The ID of the order.
    conn (psycopg2.extensions.connection): The connection to the database.
    branch_id (int): The ID of the branch.

    Returns:
    tuple: (bool, list) where the first element is True if inventory is available for all products in the order, False otherwise,
           and the second element is a list of products with insufficient inventory.
    """
    cursor = conn.cursor()
    insufficient_products = []

    try:
        # Fetch the product details for the given order, including product name and variant
        cursor.execute("""
            SELECT od.productid, od.quantity, p.name, p.variant
            FROM orderdetails od
            JOIN products p ON od.productid = p.productid
            WHERE od.orderid = %s
        """, (order_id,))

        order_details = cursor.fetchall()

        # Check the inventory for each product in the order
        for product_id, order_quantity, product_name, product_variant in order_details:
            cursor.execute("""
                SELECT quantity
                FROM stock
                WHERE product_id = %s AND branch_id = %s
            """, (product_id, branch_id))

            inventory_record = cursor.fetchone()

            if inventory_record is None:
                # If there's no inventory record for the product in the branch, assume it's unavailable
                insufficient_products.append((product_name, product_variant, order_quantity, 0))
                continue

            inventory_quantity = inventory_record[0]

            if inventory_quantity < order_quantity:
                # If there's not enough inventory for the product, add to the list
                insufficient_products.append((product_name, product_variant, order_quantity, inventory_quantity))

        # If there are any insufficient products, return False and the list of them
        if insufficient_products:
            return False, insufficient_products

        # If all products have sufficient inventory, return True and an empty list
        return True, []

    except Exception as e:
        logging.error(f"Error checking inventory availability: {e}")
        return False, []

    finally:
        cursor.close()


@app.route('/update_order_status', methods=['POST'])
def update_order_status():
    data = request.get_json()
    order_id = data.get('order_id')
    new_status = data.get('order_status')

    if not order_id or not new_status:
        return jsonify({'error': 'Order ID and status are required'}), 400

    conn = connect_db()
    if not conn:
        logging.error("Failed to connect to the database")
        return jsonify({'error': 'Failed to connect to the database'}), 500

    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE orders SET statusid = %s WHERE orderid = %s", (new_status, order_id))
        conn.commit()
        return jsonify({'message': 'Order status updated successfully'})
    except Exception as e:
        conn.rollback()
        logging.error(f"Database update failed: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/update_order_field', methods=['POST'])
def update_order_field():
    data = request.get_json()
    order_id = data.get('order_id')
    field_name = data.get('field_name')
    new_value = data.get('new_value')

    valid_fields = {
        'source': 'sourceid',
        'pricing_mode': 'pricing_mode_id',
        'service_type': 'serviceid',
        'payment_status': 'paymentstatus',
        'branch_id': 'branch_id',
        'receiving_branch_id': 'receiving_branch_id'  # Added receiving_branch_id
    }
    print(valid_fields)

    if not order_id or field_name not in valid_fields or not new_value:
        return jsonify({'error': 'Order ID, valid field name, and new value are required'}), 400

    column_name = valid_fields[field_name]

    conn = connect_db()
    if not conn:
        logging.error("Failed to connect to the database")
        return jsonify({'error': 'Failed to connect to the database'}), 500

    cursor = conn.cursor()
    try:
        query = f"UPDATE orders SET {column_name} = %s WHERE orderid = %s"
        cursor.execute(query, (new_value, order_id))
        conn.commit()
        return jsonify({'message': f'{field_name.capitalize()} updated successfully'})
    except Exception as e:
        conn.rollback()
        logging.error(f"Database update failed: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/send_email', methods=['POST'])
def send_email():
    data = request.json
    recipient = data.get('recipient')
    subject = data.get('subject')
    message = data.get('message')
    order_id = data.get('order_id')

    if not recipient or not subject or not message or not order_id:
        return jsonify(success=False, message="All fields are required."), 400

    try:
        # Send the email (this is just an example, adapt to your email sending method)
        send_email_function(recipient, subject, message, order_id)
        return jsonify(success=True)
    except Exception as e:
        logging.error(f"Error sending email: {e}")
        return jsonify(success=False, message=str(e)), 500


def send_email_function(recipient, subject, message, order_id):
    sender = "stanley@buzylane.com"
    password = "A1qzxsw2"

    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = recipient

    with smtplib.SMTP('smtp.ipage.com', 587) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())

def add_notification(user_id, message):
    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
            (user_id, message)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Error adding notification: {e}")
    finally:
        cursor.close()
        conn.close()


@app.route('/get_notifications', methods=['GET'])
def get_notifications():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not logged in'}), 401

    conn = connect_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, message, created_at FROM notifications WHERE user_id = %s AND is_read = FALSE ORDER BY created_at DESC",
            (user_id,)
        )

        notifications = cursor.fetchall()
        return jsonify(notifications)
    except Exception as e:
        logging.error(f"Error fetching notifications: {e}")
        return jsonify({'error': 'Error fetching notifications'}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/approve_order', methods=['POST'])
def approve_order():
    data = request.get_json()
    order_id = data.get('order_id')

    if not order_id:
        return jsonify(success=False, message="Order ID is missing."), 400

    conn = connect_db()
    if not conn:
        return jsonify(success=False, message="Database connection failed."), 500

    cursor = conn.cursor()

    try:
        # Fetch order details to get the source and destination branches
        cursor.execute("SELECT sourceid, branch_id FROM orders WHERE orderid = %s", (order_id,))
        order = cursor.fetchone()
        if not order:
            return jsonify(success=False, message="Order not found."), 404

        source_id, from_branch_id = order

        # Check if the order source is "Stock-out"
        if source_id != 5:  # Assuming 5 is the value for "Stock-out"
            return jsonify(success=False, message="Order is not a stock transfer."), 400

        # Fetch the transfer branch ID from the order details (assumed to be stored in a custom field)
        cursor.execute("SELECT transfer_branch_id FROM orders WHERE orderid = %s", (order_id,))
        transfer_branch_id = cursor.fetchone()[0]

        # Ensure the current user belongs to the receiving branch
        current_user_branch_id = session.get('branch_id')
        if current_user_branch_id != transfer_branch_id:
            return jsonify(success=False, message="You do not have permission to approve this order."), 403

        # Fetch products in the order
        cursor.execute("SELECT productid, quantity FROM orderdetails WHERE orderid = %s", (order_id,))
        products = cursor.fetchall()

        for product_id, quantity in products:
            # Update stock transactions for the sending branch (Transfer Out)
            cursor.execute("""
                INSERT INTO stock_transactions (product_id, branch_id, quantity_changed, new_quantity, transaction_type, transaction_date, notes, orderid)
                VALUES (%s, %s, %s, (SELECT quantity FROM stock WHERE product_id = %s AND branch_id = %s) - %s, 'Transfer Out', CURRENT_TIMESTAMP, 'Stock-out', %s)
            """, (product_id, from_branch_id, -quantity, product_id, from_branch_id, quantity, order_id))

            # Update stock transactions for the receiving branch (Transfer In)
            cursor.execute("""
                INSERT INTO stock_transactions (product_id, branch_id, quantity_changed, new_quantity, transaction_type, transaction_date, notes, orderid)
                VALUES (%s, %s, %s, (SELECT COALESCE(quantity, 0) FROM stock WHERE product_id = %s AND branch_id = %s) + %s, 'Transfer In', CURRENT_TIMESTAMP, 'Stock-in', %s)
            """, (product_id, transfer_branch_id, quantity, product_id, transfer_branch_id, quantity, order_id))

        conn.commit()
        return jsonify(success=True, message="Order has been approved successfully.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e))
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    CORS(app)
