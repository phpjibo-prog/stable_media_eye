# app.py content (FIXED AND DEBUGGED)
from flask import Flask, render_template, session, redirect, url_for, request, flash
import os 
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
from multi_stream_recorder import MultiStreamRecorder
from fingerprint_engine import FingerprintEngine
from radio_manager import RadioManager

# Initialize fingerprint system once when the app starts
fingerprint = FingerprintEngine(
    # Change the default from None (which is the default of os.environ.get) 
    # to an empty string. The actual host is a long string.
    db_host=os.environ.get('MYSQLHOST', ''), 
    db_user=os.environ.get('MYSQLUSER', ''),
    db_password=os.environ.get('MYSQLPASSWORD', ''),
    db_name=os.environ.get('MYSQLDATABASE', ''),
    db_port=os.environ.get('MYSQLPORT', 3306)
)

# fingerprint = FingerprintEngine(
#     db_host="127.0.0.1",
#     db_user="root",
#     db_password="",
#     db_name="media_daily_eye_db"
# )

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp3'}

IMAGE_FOLDER = "static/radio_icons"
ALLOWED_IMAGES = {"png", "jpg", "jpeg"}


os.makedirs(IMAGE_FOLDER, exist_ok=True)

print("=== MYSQL ENV DEBUG ===")
print("HOST:", os.environ.get("MYSQLHOST"))
print("USER:", os.environ.get("MYSQLUSER"))
print("DB:", os.environ.get("MYSQLDATABASE"))
print("PORT:", os.environ.get("MYSQLPORT"))
print("=======================")

app = Flask(__name__)
app.secret_key = 'jibostable' # !! REQUIRED !!
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER # Configure Flask for upload
app.config["IMAGE_FOLDER"] = IMAGE_FOLDER

# Database Configuration (Update with your credentials)
DB_CONFIG = {
    'host': os.environ.get('MYSQLHOST', ''),
    'user': os.environ.get('MYSQLUSER', ''),
    'password': os.environ.get('MYSQLPASSWORD', ''),
    'database': os.environ.get('MYSQLDATABASE', ''), 
    'port': os.environ.get('MYSQLPORT', 3306)
}

# DB_CONFIG = {
#     'host': 'localhost',
#     'user': 'root',
#     'password': '',
#     'database': 'media_daily_eye_db'
# }

radio_manager = RadioManager(DB_CONFIG)
STREAMS = [
    "https://eatv.radioca.st/stream",
    "https://s3.radio.co/s8df0149e0/listen",
    "hhttps://cast.tunzilla.com/http://usa1-vn.mixstream.net:8090/;listen.mp3",
]



def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGES


def get_db_connection():
    """Establishes a new database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def allowed_file(filename): # <-- Needed for upload logic
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if the user is logged in AND if they have the 'is_admin' flag set in their session
        is_admin = session.get('user_data', {}).get('is_admin')
        if not session.get('logged_in') or not is_admin:
            flash('Unauthorized access: Admins only.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function to get the data you asked for
def get_user_activity(user_id):
    conn = get_db_connection()
    data = {
        'uploaded': [],
        'following': [],
        'online_users': []
    }
    
    if not conn:
        print("Database connection failed.")
        return data
    
    cursor = conn.cursor(dictionary=True)

    try:
        # -------------------------------
        # 1. GET USER UPLOADED TRACKS
        # -------------------------------
        cursor.execute("""
            SELECT track_id 
            FROM user_tracks 
            WHERE user_id = %s
        """, (user_id,))
        uploaded_rows = cursor.fetchall()

        # FIXED HERE
        data['uploaded'] = [row['track_id'] for row in uploaded_rows]

        # -------------------------------
        # 2. GET FOLLOWED SONGS
        # -------------------------------
        cursor.execute("""
            SELECT 
                f.song_id,
                f.custom_name,
                s.song_name
            FROM user_follows f
            LEFT JOIN songs s ON f.song_id = s.song_id
            WHERE f.user_id = %s
        """, (user_id,))

        follow_rows = cursor.fetchall()

        data['following'] = [
            {
                "song_id": row["song_id"],
                "name": row["custom_name"] if row["custom_name"] else (row["song_name"] or "Unknown Song"),
                "original_name": row["song_name"] if row["song_name"] else "Song Not Found"
            }
            for row in follow_rows
        ]

        # -------------------------------
        # 3. GET ONLINE USERS
        # -------------------------------
        cursor.execute("""
            SELECT username 
            FROM users
            WHERE last_seen > (NOW() - INTERVAL 30 MINUTE)
        """)
        online = cursor.fetchall()

        data['online_users'] = [r["username"] for r in online]

    except Exception as e:
        print("Error reading user activity:", e)

    finally:
        cursor.close()
        conn.close()

    return data


# Add this function to track online status (runs before every request)
@app.before_request
def update_last_seen():
    if session.get('logged_in'):
        user_id = session.get('user_data', {}).get('db_id')
        if user_id:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("UPDATE users SET last_seen = NOW() WHERE id = %s", (user_id,))
                    conn.commit()
                    # --- DEBUGGING PRINT ---
                    print(f"DEBUG: Successfully updated last_seen for user ID {user_id}.") 
                except Error as e:
                    print(f"Error updating last_seen: {e}") 
                finally:
                    if cursor: cursor.close()
                    if conn: conn.close()
            
@app.route('/')
def home():
    logged_in = session.get('logged_in', False)
    # 1. Fetch radio data
    all_radios = radio_manager.get_all_radios()
    
    # 2. Pass data to the template
    return render_template(
        'index.html', 
        title='Homepage', 
        logged_in=logged_in, 
        all_radios=all_radios # <-- NEW CONTEXT VARIABLE
    )

@app.route("/db-test")
def db_test():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = cur.fetchall()
        cur.close()
        conn.close()
        return f"CONNECTED ✅ Tables: {tables}"
    except Exception as e:
        return f"DB FAILED ❌ {e}"

@app.route("/start-recorder")
def start_recorder():
    recorder = MultiStreamRecorder(DB_CONFIG)
    recorder.start()
    return "Recorder started"

@app.route('/about')
def about():
    logged_in = session.get('logged_in', False)
    return render_template('about.html', title='About Page', logged_in=logged_in)

@app.route('/contact')
def contact():
    logged_in = session.get('logged_in', False)
    return render_template('contact.html', title='Contact Page', logged_in=logged_in)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_data', None) # Clear user data on logout
    return redirect(url_for('home'))

@app.route('/upload-form-page') # <-- Added missing route for the form display page
def upload_form_page():
    """Renders the template containing the upload form or login message."""
    logged_in = session.get('logged_in', False)
    return render_template('upload_form.html', title='Upload MP3', logged_in=logged_in)

@app.route('/upload-mp3', methods=['POST'])
def upload_mp3():
    """Handles the MP3 file upload and database insertion."""
    
    if not session.get('logged_in'):
        flash('You must be logged in to upload a track.', 'error')
        return redirect(url_for('upload_form_page'))

    user_id = session.get('user_data', {}).get('db_id') 
    if not user_id:
        flash('Could not find associated user account data in session. Please log in again.', 'error')
        return redirect(url_for('upload_form_page'))

    track_name = request.form.get('track_name')
    if not track_name:
        flash('Track name is required.', 'error')
        return redirect(url_for('upload_form_page'))
        
    if 'mp3_file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('upload_form_page'))
    
    file = request.files['mp3_file']

    if file.filename == '':
        flash('No selected file.', 'error')
        return redirect(url_for('upload_form_page'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(file_path)
        except IOError as e:
            flash(f"Error saving file to disk: {e}", 'error')
            return redirect(url_for('upload_form_page'))

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                sql_insert_query = """
                    INSERT INTO user_tracks (user_id, track_name, file_path, upload_time) 
                    VALUES (%s, %s, %s, NOW())
                """
                insert_data = (user_id, track_name, file_path)
                
                cursor.execute(sql_insert_query, insert_data)
                conn.commit() 
                flash('Track uploaded and recorded successfully!', 'success')
                print('trying to fingerprint')
                
            except Error as e:
                flash(f"Database error during track insertion: {e}", 'error')
                conn.rollback() 
            finally:
                cursor.close()
                conn.close()
        else:
            flash("Could not connect to the database to finalize upload.", 'error')
            
    else:
        flash('Invalid file type. Only MP3 files are allowed.', 'error')
    fingerprint_all()
    return redirect(url_for('upload_form_page'))

@app.route("/fingerprint_all")
def fingerprint_all():
    try:
        fingerprint.fingerprint_folder("uploads")
        return "Fingerprinting completed!"
    except Exception as e:
        return f"Error: {e}"

@app.route('/login_simulation')
def login_simulation():
    provider = request.args.get('provider', 'unknown')

    sample_user_data = {
        'username': 'SampleUser123',
        'email': 'user@example.com',
        'social_provider': provider
    }

    conn = get_db_connection()
    if not conn:
        return redirect(url_for('home'))

    cursor = conn.cursor(dictionary=True)

    try:
        # 🔥 FIX: Use dynamic email matching
        cursor.execute("SELECT * FROM users WHERE email = %s", (sample_user_data['email'],))
        user = cursor.fetchone()

        if user:
            user_id = user['id']
            is_admin_status = user['is_admin']

        else:
            # 🔥 FIX: Insert correct user only once
            cursor.execute("""
                INSERT INTO users (username, email, social_provider)
                VALUES (%s, %s, %s)
            """, (sample_user_data['username'], sample_user_data['email'], provider))
            conn.commit()
            user_id = cursor.lastrowid
            is_admin_status = 0

        # 🔥 IMPORTANT: Store correct user_id in session
        session['logged_in'] = True
        session['user_data'] = {
            'username': sample_user_data['username'],
            'email': sample_user_data['email'],
            'db_id': user_id,
            'is_admin': is_admin_status,
            'social_provider': provider
        }

        print("LOGGED IN AS USER ID:", user_id)

    except Exception as e:
        print("Login error:", e)

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('account'))

@app.route('/admin-dashboard')
@admin_required 
def admin_dashboard():
    """Renders the admin-only dashboard page."""
    return render_template('admin_dashboard.html', title='Admin Dashboard', logged_in=True)

@app.route('/admin-add-radio', methods=['POST'])
@admin_required
def admin_add_radio():
    # 1. Get Text Data
    radio_name = request.form.get('radio_name')
    stream_link = request.form.get('stream_link')
    country_name = request.form.get('country_name')
    region_name = request.form.get('region_name') or None 

    # 2. Get File Data
    icon_file = request.files.get('radio_icon')

    # 3. Validate Text Fields
    if not radio_name or not stream_link or not country_name:
        flash('Missing required fields: Name, Link, and Country are mandatory.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # 4. Handle Image Upload
    icon_filename = None
    icon_path = None
    icon_size = 0

    if icon_file and icon_file.filename != "":
        if not allowed_image(icon_file.filename):
            flash("Invalid image type. Only PNG/JPG allowed.", "error")
            return redirect(url_for('admin_dashboard'))

        try:
            icon_filename = secure_filename(icon_file.filename)
            
            # --- CRITICAL FIX: Use os.path.join, THEN REPLACE '\' with '/' ---
            # 1. Create the OS-specific path for saving the file
            save_path = os.path.join(app.config['IMAGE_FOLDER'], icon_filename)
            
            icon_file.save(save_path) 

            icon_path_db = "radio_icons/{}".format(icon_filename)
            
            icon_size = os.path.getsize(save_path)

            # 2. Create the URL-safe path for the database
            icon_path = save_path.replace(os.path.sep, '/') # This changes '\' to '/'
            print(f"[UPLOAD] Saved icon → {save_path} ({icon_size} bytes)")
            
        except Exception as e:
            flash(f"Failed to save icon: {e}", "error")
            return redirect(url_for('admin_dashboard'))
    else:
        flash("Radio icon is required.", "error")
        return redirect(url_for('admin_dashboard'))

    # 5. Insert into Database
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            sql_insert_query = """
                INSERT INTO radios (radio_name, stream_link, country_name, region_name,
                     icon_filename, icon_path, icon_size)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            insert_data = (radio_name, stream_link, country_name, region_name, icon_filename, icon_path_db, icon_size)
            
            cursor.execute(sql_insert_query, insert_data)
            conn.commit()
            flash(f'Successfully added new radio station: {radio_name}', 'success')

        except Error as e:
            flash(f"Database error when adding radio: {e}", 'error')
            conn.rollback() 
        finally:
            cursor.close()
            conn.close()
    else:
        flash("Database connection failed.", 'error')

    return redirect(url_for('admin_dashboard'))

@app.route('/follow-song', methods=['POST'])
def follow_song():
    if not session.get('logged_in'):
        flash('You must be logged in to follow a song.', 'error')
        return redirect(url_for('account'))
    
    user_id = session.get('user_data', {}).get('db_id')
    song_id = request.form.get('song_id', type=int)
    custom_name = request.form.get('custom_name') or None 
    
    if not user_id or not song_id:
        flash('Invalid user or song ID.', 'error')
        return redirect(url_for('account'))
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            # Check if the user is already following the song
            cursor.execute("SELECT id FROM user_follows WHERE user_id = %s AND song_id = %s", (user_id, song_id))
            if cursor.fetchone():
                # If following, update the custom name
                sql_update_query = """
                    UPDATE user_follows 
                    SET custom_name = %s 
                    WHERE user_id = %s AND song_id = %s
                """
                cursor.execute(sql_update_query, (custom_name, user_id, song_id))
                flash(f'Successfully updated custom name for song ID {song_id}.', 'success')
            else:
                # If not following, insert the new follow record
                sql_insert_query = """
                    INSERT INTO user_follows (user_id, song_id, custom_name)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(sql_insert_query, (user_id, song_id, custom_name))
                flash(f'Successfully followed song ID {song_id}!', 'success')
                
            conn.commit()
            
        except Error as e:
            flash(f"Database error when following song: {e}", 'error')
            conn.rollback() 
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    else:
        flash("Database connection failed.", 'error')

    return redirect(url_for('account'))

            
@app.route('/account')
def account():
    logged_in = session.get('logged_in', False)
    user_data = session.get('user_data')

    print("DEBUG: Logged in =", logged_in)
    print("DEBUG: Session user_data =", user_data)

    if not logged_in or not user_data or not user_data.get('db_id'):
        flash('Please log in to view your account.', 'error')
        return redirect(url_for('home'))

    user_id = user_data.get('db_id')

    print("DEBUG: USER_ID used for query =", user_id)

    # SAFE default structure to avoid crashes
    activity_data = {
        'uploaded': [],
        'following': [],
        'online_users': []
    }

    # Attempt to load data but never break the route
    try:
        activity_data = get_user_activity(user_id)
        print("DEBUG: Following songs returned =", activity_data['following'])
    except Exception as e:
        print("CRITICAL ERROR in account():", e)

    # 🔥 ALWAYS RETURN A TEMPLATE
    return render_template(
        'account.html',
        user=user_data,
        title='Account Page',
        logged_in=logged_in,
        uploaded_ids=activity_data.get('uploaded', []),
        following_songs=activity_data.get('following', []),
        online_users=activity_data.get('online_users', [])
    )


if __name__ == '__main__':
    #recorder.start()          # Start background radio recording
    print(">>> Recorder Started <<<")
    app.run(debug=True)
