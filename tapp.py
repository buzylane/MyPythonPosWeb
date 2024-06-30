import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, ConversationHandler, \
    CallbackQueryHandler

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection parameters
DB_NAME = "awsdb"
DB_USER = "postgres"
DB_PASSWORD = "1qazxsw2"
DB_HOST = "buzylaneawsdb.cdu6akewglav.eu-north-1.rds.amazonaws.com"  # This will be something like "your-db-instance.xxxxxxxxxx.us-east-1.rds.amazonaws.com"
DB_PORT = "5432"  # Default PostgreSQL port

# States for conversation
REGISTER, REGISTER_PASSWORD, LOGIN, LOGIN_PASSWORD, MENU, CREATE_EVENT_NAME, CREATE_EVENT_DESCRIPTION, CREATE_EVENT_LOCATION, CREATE_EVENT_TIME, CREATE_EVENT_MAP_DIRECTION, REGISTER_EVENT_ID, REGISTER_NAME, REGISTER_CONTACT, EVENT_DETAILS_ID = range(
    14)


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
    except Exception as e:
        logger.error("Unable to connect to the database: %s", e)
        return None


def create_tables():
    conn = connect_db()
    if not conn:
        logger.error("Failed to create tables due to database connection issue.")
        return

    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS events (
        id SERIAL PRIMARY KEY,
        creator_id INTEGER,
        name TEXT,
        description TEXT,
        location TEXT,
        time TEXT,
        map_direction TEXT
    );
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS registrations (
        id SERIAL PRIMARY KEY,
        event_id INTEGER,
        name TEXT,
        contact TEXT
    );
    ''')
    conn.commit()
    cursor.close()
    conn.close()


create_tables()


def start(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Welcome! Please register or login.\nSend /register to register or /login to login.')
    return ConversationHandler.END


def register(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Enter username:')
    return REGISTER


def register_username(update: Update, context: CallbackContext) -> int:
    context.user_data['username'] = update.message.text
    update.message.reply_text('Enter password:')
    return REGISTER_PASSWORD


def register_password(update: Update, context: CallbackContext) -> int:
    username = context.user_data['username']
    password = update.message.text

    conn = connect_db()
    if not conn:
        update.message.reply_text('Database connection failed. Please try again later.')
        return ConversationHandler.END

    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, password))
        conn.commit()
        update.message.reply_text('Registration successful. Please login with /login.')
    except psycopg2.IntegrityError:
        conn.rollback()
        update.message.reply_text('Username already exists. Please try again.')
    cursor.close()
    conn.close()

    return ConversationHandler.END


def login(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Enter username:')
    return LOGIN


def login_username(update: Update, context: CallbackContext) -> int:
    context.user_data['username'] = update.message.text
    update.message.reply_text('Enter password:')
    return LOGIN_PASSWORD


def login_password(update: Update, context: CallbackContext) -> int:
    username = context.user_data['username']
    password = update.message.text

    conn = connect_db()
    if not conn:
        update.message.reply_text('Database connection failed. Please try again later.')
        return ConversationHandler.END

    cursor = conn.cursor()
    cursor.execute('SELECT userid FROM users WHERE username=%s AND password=%s', (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user:
        context.user_data['user_id'] = user[0]
        update.message.reply_text('Login successful. Use /menu to continue.')
        return MENU
    else:
        update.message.reply_text('Invalid credentials. Please try again.')
        return ConversationHandler.END


def menu(update: Update, context: CallbackContext) -> int:
    keyboard = [
        [InlineKeyboardButton("Create Event", callback_data='create_event')],
        [InlineKeyboardButton("Get List", callback_data='get_list')],
        [InlineKeyboardButton("Register to Event", callback_data='register_event')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Check if update is from a command or callback query
    if update.callback_query:
        update.callback_query.message.reply_text('Please choose:', reply_markup=reply_markup)
    else:
        update.message.reply_text('Please choose:', reply_markup=reply_markup)
    return MENU

def button(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    if query.data == 'create_event':
        query.edit_message_text(text="Enter event name:")
        return CREATE_EVENT_NAME
    elif query.data == 'get_list':
        update.callback_query.edit_message_text(text="Fetching list...")
        return get_list(update, context)
    elif query.data == 'register_event':
        query.edit_message_text(text="Enter Event ID:")
        return REGISTER_EVENT_ID

def get_list(update: Update, context: CallbackContext) -> int:
    conn = connect_db()
    if not conn:
        update.callback_query.edit_message_text(text='Database connection failed. Please try again later.')
        return MENU

    cursor = conn.cursor()
    cursor.execute('SELECT id, name, description FROM events')
    events = cursor.fetchall()
    cursor.close()
    conn.close()

    message_text = 'Available Events:\n' + '\n'.join([f'ID: {event[0]}, Name: {event[1]}, Desc: {event[2]}' for event in events])
    update.callback_query.edit_message_text(text=message_text)
    return EVENT_DETAILS_ID


def create_event_name(update: Update, context: CallbackContext) -> int:
    context.user_data['event_name'] = update.message.text
    update.message.reply_text('Enter event description:')
    return CREATE_EVENT_DESCRIPTION


def create_event_description(update: Update, context: CallbackContext) -> int:
    context.user_data['event_description'] = update.message.text
    update.message.reply_text('Enter event location:')
    return CREATE_EVENT_LOCATION


def create_event_location(update: Update, context: CallbackContext) -> int:
    context.user_data['event_location'] = update.message.text
    update.message.reply_text('Enter event time:')
    return CREATE_EVENT_TIME


def create_event_time(update: Update, context: CallbackContext) -> int:
    context.user_data['event_time'] = update.message.text
    update.message.reply_text('Enter event map direction:')
    return CREATE_EVENT_MAP_DIRECTION


def create_event_map_direction(update: Update, context: CallbackContext) -> int:
    user_id = context.user_data['user_id']
    name = context.user_data['event_name']
    description = context.user_data['event_description']
    location = context.user_data['event_location']
    time = context.user_data['event_time']
    map_direction = update.message.text

    conn = connect_db()
    if not conn:
        update.message.reply_text('Database connection failed. Please try again later.')
        return ConversationHandler.END

    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO events (creator_id, name, description, location, time, map_direction) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id',
        (user_id, name, description, location, time, map_direction))
    event_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    update.message.reply_text(f'Event created successfully. Event ID: {event_id}')
    return MENU


def event_details(update: Update, context: CallbackContext) -> int:
    event_id = update.message.text
    conn = connect_db()
    if not conn:
        update.message.reply_text('Database connection failed. Please try again later.')
        return ConversationHandler.END

    cursor = conn.cursor()
    cursor.execute('SELECT name, contact FROM registrations WHERE event_id=%s', (event_id,))
    registrants = cursor.fetchall()
    cursor.close()
    conn.close()

    if registrants:
        for registrant in registrants:
            update.message.reply_text(f'Name: {registrant[0]}\nContact: {registrant[1]}')
    else:
        update.message.reply_text('No registrants found for this event.')

    return MENU


def register_event(update: Update, context: CallbackContext) -> int:
    context.user_data['event_id'] = update.message.text
    update.message.reply_text('Enter your name:')
    return REGISTER_NAME


def register_name(update: Update, context: CallbackContext) -> int:
    context.user_data['register_name'] = update.message.text
    update.message.reply_text('Enter your contact:')
    return REGISTER_CONTACT


def register_contact(update: Update, context: CallbackContext) -> int:
    event_id = context.user_data['event_id']
    name = context.user_data['register_name']
    contact = update.message.text

    conn = connect_db()
    if not conn:
        update.message.reply_text('Database connection failed. Please try again later.')
        return ConversationHandler.END

    cursor = conn.cursor()
    cursor.execute('INSERT INTO registrations (event_id, name, contact) VALUES (%s, %s, %s)', (event_id, name, contact))
    conn.commit()
    cursor.close()
    conn.close()

    update.message.reply_text('Registration successful.')
    return MENU


def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Operation cancelled.')
    return MENU


def main() -> None:
    updater = Updater("6403489314:AAFzLZhot5aAYOSXdVU-21tud6RIsHeVKpY", use_context=True)

    dispatcher = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('register', register),
            CommandHandler('login', login),
            CommandHandler('menu', menu)  # Ensure menu can be triggered directly
        ],
        states={
            REGISTER: [MessageHandler(Filters.text & ~Filters.command, register_username)],
            REGISTER_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, register_password)],
            LOGIN: [MessageHandler(Filters.text & ~Filters.command, login_username)],
            LOGIN_PASSWORD: [MessageHandler(Filters.text & ~Filters.command, login_password)],
            MENU: [CallbackQueryHandler(button)],
            CREATE_EVENT_NAME: [MessageHandler(Filters.text & ~Filters.command, create_event_name)],
            CREATE_EVENT_DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, create_event_description)],
            CREATE_EVENT_LOCATION: [MessageHandler(Filters.text & ~Filters.command, create_event_location)],
            CREATE_EVENT_TIME: [MessageHandler(Filters.text & ~Filters.command, create_event_time)],
            CREATE_EVENT_MAP_DIRECTION: [MessageHandler(Filters.text & ~Filters.command, create_event_map_direction)],
            EVENT_DETAILS_ID: [MessageHandler(Filters.text & ~Filters.command, event_details)],
            REGISTER_EVENT_ID: [MessageHandler(Filters.text & ~Filters.command, register_event)],
            REGISTER_NAME: [MessageHandler(Filters.text & ~Filters.command, register_name)],
            REGISTER_CONTACT: [MessageHandler(Filters.text & ~Filters.command, register_contact)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dispatcher.add_handler(conv_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
