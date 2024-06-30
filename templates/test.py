from flask import jsonify, Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

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
        print(f"Database connection failed: {e}")
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
            cursor.execute("SELECT userid, username FROM users WHERE username = %s AND password = %s",
                           (username, password))
            user_record = cursor.fetchone()
            cursor.close()
            conn.close()
            if user_record:
                session['user_id'] = user_record[0]
                session['username'] = user_record[1]
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
    order_id = request.args.get('order_id')
    conn = connect_db()
    customers = []
    order_details = None
    order_sources = []
    pricing_modes = []
    service_types = []
    order_statuses = []
    payment_statuses = []

    if request.method == 'POST':
        try:
            customer_id = request.form.get('Customer_ID', '1')
            source = request.form.get('source', '0')
            service = request.form.get('service_type', '0')
            total_amount = request.form.get('order_amount', '0.00')
            discount = request.form.get('total_discount', '0.00')
            status = request.form.get('order_status', '0')
            payment_status = request.form.get('payment_status', '0')
            user_id = session.get('user_id')

            if order_id:
                query = """
                UPDATE orders SET 
                    customerid = %s, sourceid = %s, serviceid = %s, totalamount = %s, 
                    discount = %s, statusid = %s, paymentstatus = %s, userid = %s
                WHERE orderid = %s
                """
                params = (customer_id, source, service, total_amount, discount, status, payment_status, user_id, order_id)
                return redirect(url_for('add_order', order_id=order_id))
            else:
                query = """
                INSERT INTO orders (customerid, sourceid, serviceid, totalamount, discount, statusid, paymentstatus, userid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING orderid
                """
                params = (customer_id, source, service, total_amount, discount, status, payment_status, user_id)
                print(params)
                cursor = conn.cursor()
                cursor.execute(query, params)
                order_id = cursor.fetchone()[0]  # Fetch the returned order_id from INSERT operation
                conn.commit()
                cursor.close()

            flash('Order saved successfully!', 'success')
            return redirect(url_for('add_order', order_id=order_id))
        except KeyError as e:
            flash(f'Missing form field: {e.args[0]}', 'danger')
        except Exception as e:
            if conn:
                conn.rollback()  # Rollback the transaction on error
                conn.close()
            flash(f'Error saving order: {str(e)}', 'danger')
        return redirect(url_for('add_order'))

    if conn:
        try:
            cursor = conn.cursor()
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

            if order_id:
                cursor.execute("SELECT * FROM orders WHERE orderid = %s", (order_id,))
                order_details = cursor.fetchone()

            cursor.close()
        except Exception as e:
            flash(f'Error fetching data: {str(e)}', 'danger')
        finally:
            conn.close()

    default_customer_name = customers[0][1] if customers else ''
    default_customer_contact = customers[0][2] if customers else ''
    default_order_status = order_statuses[0][0] if order_statuses else ''
    default_payment_status = payment_statuses[0][0] if payment_statuses else ''
    print(default_payment_status,default_order_status)

    return render_template('add_order.html',
                           customers=customers,
                           order_details=order_details,
                           order_sources=order_sources,
                           pricing_modes=pricing_modes,
                           service_types=service_types,
                           order_statuses=order_statuses,
                           order_ids=order_ids,
                           payment_statuses=payment_statuses,
                           default_customer_name=default_customer_name,
                           default_customer_contact=default_customer_contact,
                           default_order_status=default_order_status,
                           default_payment_status=default_payment_status)


@app.route('/get_product_details', methods=['GET'])
def get_product_details():
    product_id = request.args.get('productId')
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
                        'supplierid': product[12]
                    })
                else:
                    return jsonify({'error': 'Product not found'})
            except Exception as e:
                print(f"Database query failed: {e}")
                return jsonify({'error': 'Query failed'})
            finally:
                cursor.close()
                conn.close()
    return jsonify({'error': 'Invalid product code'})



@app.route('/get_product_details_by_name', methods=['GET'])
def get_product_details_by_name():
    product_name = request.args.get('product_name')
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
                print(f"Database query failed: {e}")
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
        # Example query to get number of orders
        cursor.execute("SELECT COUNT(*) FROM orders")
        data['order_count'] = cursor.fetchone()[0]

        # Example query to get total sales
        cursor.execute("SELECT SUM(totalamount) FROM orders")
        data['total_sales'] = cursor.fetchone()[0]

        # Add more queries as needed for different dashboard metrics
        cursor.execute("SELECT COUNT(*) FROM customers")
        data['customer_count'] = cursor.fetchone()[0]

    except Exception as e:
        print(f"Failed to fetch dashboard data: {e}")
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
                print(f"Database query failed: {e}")
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
                    SELECT DISTINCT productid, name
                    FROM products
                    WHERE CAST(productid AS TEXT) ILIKE %s OR LOWER(name) ILIKE %s
                """, (f"%{query.lower()}%", f"%{query.lower()}%"))
                products = cursor.fetchall()
                return jsonify(products)
            except Exception as e:
                print(f"Database query failed: {e}")
                return jsonify([])
            finally:
                cursor.close()
                conn.close()
    return jsonify([])

# @app.route('/search_products', methods=['GET'])
# def search_products():
#     query = request.args.get('query')
#     if query:
#         conn = connect_db()
#         if conn:
#             cursor = conn.cursor()
#             try:
#                 cursor.execute("""
#                     SELECT DISTINCT productid, name
#                     FROM products
#                     WHERE CAST(productid AS TEXT) ILIKE %s OR LOWER(name) ILIKE %s
#                 """, (f"%{query.lower()}%", f"%{query.lower()}%"))
#                 products = cursor.fetchall()
#                 return jsonify(products)
#             except Exception as e:
#                 print(f"Database query failed: {e}")
#                 return jsonify([])
#             finally:
#                 cursor.close()
#                 conn.close()
#     return jsonify([])



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
                print(f"Database query failed: {e}")
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
                cursor.execute("SELECT variant FROM products WHERE name = %s ORDER BY variant" , (product_name,))
                variants = cursor.fetchall()
                return jsonify([variant[0] for variant in variants])
            except Exception as e:
                print(f"Database query failed: {e}")
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
        cursor.execute("SELECT * FROM orders WHERE orderid = %s", (order_id,))
        order = cursor.fetchone()
        cursor.close()
        conn.close()

        if order:
            order_details = {
                'order_id': order[0],
                'customer_id': order[1],
                'order_date': order[9],
                'source': order[4],
                'service': order[3],
                'total_amount': order[5],
                'discount': order[6],
                'total': order[5],
                'status': order[2],
                'payment_status': order[14],
                'delivery_date': order[9],
                'customer_name': order[2],  # Adjust if necessary
                'customer_contact': order[2]  # Adjust if necessary
            }

            return jsonify(order_details)
    return jsonify({'error': 'Order not found'})

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
            # Format the data for DataTables
            orders_list = []
            for order in orders:
                orders_list.append({
                    "order_id": order[0],
                    "customer_name": order[1],
                    "date": order[2].strftime('%Y-%m-%d'),  # Formatting date
                    "status": order[3],
                    "total_amount": f"¢{order[4]:,.2f}",  # Formatting as currency
                    "actions": f"<button class='btn btn-info' onclick='viewOrder({order[0]})'>View</button>"  # Adding a button for actions
                })
            return jsonify(orders_list)
        except Exception as e:
            print(f"Database query failed: {e}")
            return jsonify([]), 500  # Return an empty list in case of error
        finally:
            conn.close()
    else:
        return jsonify([]), 500  # Return an empty list if DB connection fails


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
                print(f"Database query failed: {e}")
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
            'subcategory': p[13]
        } for p in products])
    return jsonify([])




@app.route('/edit_product', methods=['POST'])
def edit_product():
    data = request.form.to_dict()
    product_id = data['product_id']
    name = data.get('name')
    variant = data.get('variant')
    quantity = data.get('quantity')
    retailprice = data.get('retailprice')
    promoprice = data.get('promoprice')
    wholesaleprice = data.get('wholesaleprice')
    supplierprice = data.get('supplierprice')

    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE products SET name = %s, variant = %s, quantity = %s, retailprice = %s, promoprice = %s,
                wholesaleprice = %s, supplierprice = %s
                WHERE productid = %s
            """, (name, variant, quantity, retailprice, promoprice, wholesaleprice, supplierprice, product_id))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'status': 'success'})
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'status': 'error', 'message': str(e)})
    return jsonify({'status': 'error', 'message': 'Failed to connect to database'})


@app.route('/add_product', methods=['POST'])
def add_product():
    conn = connect_db()
    if conn:
        data = request.form.to_dict()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO products (name, variant, quantity, retailprice, promoprice, wholesaleprice, supplierprice)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (data['name'], data['variant'], data['quantity'], data['retailprice'], data['promoprice'],
                  data['wholesaleprice'], data['supplierprice']))
            conn.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            print(f"Error adding product: {e}")
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
                print(f"Database query failed: {e}")
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
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT subcategoryid, subcategoryname FROM productsubcategory WHERE categoryid = %s ORDER BY subcategoryname", (category_id,))
    subcategories = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{'subcategoryid': s[0], 'name': s[1]} for s in subcategories])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    CORS(app)