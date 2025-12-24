# app.py content (FIXED AND DEBUGGED)
from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify
import os 
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from functools import wraps
from multi_stream_recorder import MultiStreamRecorder
from fingerprint_engine import FingerprintEngine
from radio_manager import RadioManager
from user_tracker import UserTracker
from youtube_downloader import download_youtube_as_mp3
from pydub import AudioSegment
import requests
import time
import numpy as np
from flask import send_from_directory
import json
import subprocess
from yt_fetcher import fetch_youtube_formats
from youtube_formats import get_youtube_formats

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
#     db_name="media_daily_eye_db",
#     db_port= 3306
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
#     'database': 'media_daily_eye_db',
#     'port': 3306
# }

radio_manager = RadioManager(DB_CONFIG)
user_tracker = UserTracker(DB_CONFIG)
STREAMS = [
    "https://eatv.radioca.st/stream",
    "https://s3.radio.co/s8df0149e0/listen",
    "hhttps://cast.tunzilla.com/http://usa1-vn.mixstream.net:8090/;listen.mp3",
]

recorder = MultiStreamRecorder(DB_CONFIG)

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

def calculate_date_range(date_type, date_value):
    """
    Calculates precise start_date and end_date datetime objects 
    from the user's input type (date, week, month) and value.
    """
    start_date = None
    end_date = None
    
    try:
        if date_type == 'date' and date_value:
            # Format: 'YYYY-MM-DD'
            start_date = datetime.strptime(date_value, '%Y-%m-%d')
            end_date = start_date + timedelta(days=1) - timedelta(seconds=1) # End of the selected day

        elif date_type == 'week' and date_value:
            # Format: 'YYYY-Wnn' (e.g., '2025-W51')
            year, week_num = map(int, date_value.split('-W'))
            # Monday of the given week
            start_date = datetime.strptime(f'{year}-W{week_num}-1', '%Y-W%W-%w')
            end_date = start_date + timedelta(weeks=1) - timedelta(seconds=1) # End of the week (Sunday 23:59:59)

        elif date_type == 'month' and date_value:
            # Format: 'YYYY-MM'
            start_date = datetime.strptime(date_value, '%Y-%m')
            
            # Calculate the first day of the *next* month
            year = start_date.year
            month = start_date.month
            
            if month == 12:
                next_month_start = datetime(year + 1, 1, 1)
            else:
                next_month_start = datetime(year, month + 1, 1)
                
            end_date = next_month_start - timedelta(seconds=1) # End of the selected month
        
    except ValueError as e:
        print(f"Error calculating date range for {date_type}: {e}")
        # Return None, which will trigger the 7-day default in RadioManager
        return None, None
        
    return start_date, end_date

def json_serializable(data):
    """Recursively convert data to be JSON serializable."""
    if isinstance(data, dict):
        return {k: json_serializable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [json_serializable(i) for i in data]
    elif isinstance(data, bytes):
        return data.decode('utf-8', errors='ignore')
    elif isinstance(data, (np.int64, np.int32)):
        return int(data)
    elif isinstance(data, (np.float64, np.float32)):
        return float(data)
    else:
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
            
@app.route('/', methods=['GET', 'POST'])
def home():
    logged_in = session.get('logged_in', False)
    user_data = session.get('user_data', {}) # Get user data for the ID
    user_id = user_data.get('db_id')
    # 1. Fetch radio data
    # Initialize date range variables
    start_date = None
    end_date = None
    
    # 1. Handle form submission (filtering)
    if request.method == 'POST':
        # Determine which input type was used
        date_type = request.form.get('date_type') # 'date', 'week', or 'month'
        date_value = request.form.get('date_value') # The actual value from the input
        
        # Calculate the date range based on the input
        start_date, end_date = calculate_date_range(date_type, date_value)
        
        # Store the current selection in session to preserve it across page reloads
        session['filter_date_type'] = date_type
        session['filter_date_value'] = date_value
        
    else: # GET request (first load or direct navigation)
        # Check session for a previous filter selection
        date_type = session.get('filter_date_type')
        date_value = session.get('filter_date_value')
        
        if date_type and date_value:
            start_date, end_date = calculate_date_range(date_type, date_value)

    # 2. Fetch radio data, passing the calculated dates (or None/None for default)
    # The RadioManager handles the 7-day default if start_date/end_date are None
    all_radios = radio_manager.get_all_radios(start_date=start_date, end_date=end_date)
    
    # 2. Fetch total song count (NEW)
    total_songs = radio_manager.get_total_songs_count()

    user_tracks_data = []
    if logged_in and user_id:
        # Pass the calculated or default date range to the tracker
        user_tracks_data = user_tracker.get_user_tracked_plays(
            user_id=user_id, 
            start_date=start_date, 
            end_date=end_date
        )

    most_played_data = user_tracker.get_most_played_tracks(
        # Pass user_id only if logged in, otherwise None for general data
        user_id=user_id if logged_in else None,
        start_date=start_date, 
        end_date=end_date
    )
    
    # 2. Pass data to the template
    return render_template(
        'index.html', 
        title='Homepage', 
        logged_in=logged_in, 
        all_radios=all_radios,
        # NEW CONTEXT VARIABLES for template to remember the selected filter
        user_tracks_data=user_tracks_data,
        most_played_data=most_played_data,
        current_date_type=session.get('filter_date_type', 'date'), # Default to 'date'
        current_date_value=session.get('filter_date_value', ''),
        total_songs=total_songs
    )

VERIFY_FOLDER = 'static/recordings'
os.makedirs(VERIFY_FOLDER, exist_ok=True)

@app.route("/youtube-formats", methods=["GET", "POST"])
def youtube_formats():
    video_formats = []
    audio_formats = []
    youtube_url = ""

    if request.method == "POST":
        youtube_url = request.form.get("youtube_url")
        if youtube_url:
            video_formats, audio_formats = get_youtube_formats(youtube_url)

    return render_template(
        "youtube_formats.html",
        video_formats=video_formats,
        audio_formats=audio_formats,
        youtube_url=youtube_url
    )


@app.route('/api/recognize_live_stream', methods=['GET'])
def recognize_live_stream():
    stream_url = request.args.get('stream_url')
    if not stream_url:
        return "Error: Missing stream_url parameter", 400

    record_dir = 'static/recordings'
    os.makedirs(record_dir, exist_ok=True)
    
    timestamp = int(time.time())
    mp3_path = os.path.join(record_dir, f"temp_{timestamp}.mp3")
    wav_filename = f"verify_{timestamp}.wav"
    wav_path = os.path.join(record_dir, wav_filename)

    try:
        # 1. Record 10 seconds
        response = requests.get(stream_url, stream=True, timeout=15)
        max_bytes = 250000  # Cap at ~250KB to prevent the 40s issue
        bytes_recorded = 0
        start_time = time.time()
        with open(mp3_path, 'wb') as f:
            for block in response.iter_content(2048):
                f.write(block)
                if time.time() - start_time > 10:
                    break
                    
        response.close()
        # 2. Decode to WAV for high-accuracy fingerprinting
        audio = AudioSegment.from_file(mp3_path)
        audio = audio[:10000]
        audio.export(wav_path, format="wav")
        
        if os.path.exists(mp3_path):
            os.remove(mp3_path)

        # 3. Recognize using the WAV file
        raw_results = fingerprint.recognize_file(wav_path)
        clean_results = json_serializable(raw_results)

        # 4. Apply your specific logic: Hashes >= 50 AND Confidence >= 8
        matches = clean_results.get('results', [])
        is_exact_match = False
        hashes = 0
        conf = 0
        song_name = "No Match"

        if matches:
            top_match = matches[0]
            hashes = top_match.get('hashes_matched_in_input', 0)
            conf = top_match.get('input_confidence', 0)
            
            if hashes >= 50 and conf >= 8:
                is_exact_match = True
                song_name = top_match.get('song_name', 'Unknown')

        status_msg = f"MATCH FOUND: {song_name}" if is_exact_match else "MATCH REJECTED / NOT FOUND"

        # 5. Return HTML Verification Page
        return f"""
        <html>
            <body style="font-family: sans-serif; padding: 20px; line-height: 1.6;">
                <h2>Live Stream Recognition Dashboard</h2>
                <div style="background: #fdfdfd; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                    <h3 style="color: {'#28a745' if is_exact_match else '#dc3545'};">{status_msg}</h3>
                    <p><strong>Metrics:</strong> {hashes} Hashes (Target: 50) | {conf} Confidence (Target: 8)</p>
                    
                    <h4>Verification Player:</h4>
                    <p style="font-size: 0.9em; color: #666;">Listen to exactly what the system heard:</p>
                    <audio controls src="/static/recordings/{wav_filename}" style="width: 100%;"></audio>
                    
                    <div style="margin-top: 30px;">
                        <a href="/api/delete_recording?file={wav_filename}" 
                           style="background: #ff4444; color: white; padding: 12px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                           DELETE RECORDING
                        </a>
                        <a href="{request.full_path}" style="margin-left: 15px; color: #007bff;">Try Again</a>
                    </div>
                </div>
                <hr style="margin-top: 40px;">
                <h4>Raw Engine Output:</h4>
                <pre style="background: #222; color: #0f0; padding: 15px; overflow: auto; border-radius: 5px;">{json.dumps(clean_results, indent=2)}</pre>
            </body>
        </html>
        """

    except Exception as e:
        return f"Recognition failed: {str(e)}", 500
        
# 2. Add a route to manually delete the file
@app.route('/api/delete_recording')
def delete_recording():
    filename = request.args.get('file')
    if filename and 'verify_' in filename:
        file_path = os.path.join(VERIFY_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return f"File {filename} deleted. <a href='/'>Go Home</a>"
    return "Invalid file request.", 400
        
@app.route('/upload-youtube', methods=['POST'])
def upload_youtube():
    if not session.get('logged_in'):
        flash('You must be logged in to use this feature.', 'error')
        return redirect(url_for('home'))

    youtube_url = request.form.get('youtube_url')
    user_id = session.get('user_data', {}).get('db_id')
    
    if not youtube_url:
        flash("Please provide a valid URL", "error")
        return redirect(url_for('home'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # We save the URL in the 'file_path' column temporarily or a new 'url' column
        # and set status to 'pending_download'
        sql = """INSERT INTO user_tracks (user_id, track_name, file_path, status, upload_time) 
                 VALUES (%s, %s, %s, %s, NOW())"""
        cursor.execute(sql, (user_id, "YouTube Pending", youtube_url, 'pending_download'))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash("Link submitted! The worker is downloading it now.", "success")
    except Exception as e:
        print(f"Error: {e}")
        flash("Failed to queue download.", "error")

    return redirect(url_for('home'))
    
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

@app.route('/api/get_youtube_options', methods=['POST'])
def get_youtube_options():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({"success": False, "message": "No URL provided"})
    
    success, formats = fetch_youtube_formats(url)
    return jsonify({"success": success, "formats": formats if success else [], "message": "" if success else formats})

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
    return redirect(url_for('home'))

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

    return redirect(url_for('home'))

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
        all_available_songs = user_tracker.get_all_songs_with_status(user_id)
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
        online_users=activity_data.get('online_users', []),
        all_available_songs=all_available_songs
    )

@app.route('/api/toggle_follow', methods=['POST'])
def api_toggle_follow():
    """API endpoint for the Add/Remove buttons on the account page."""
    logged_in = session.get('logged_in', False)
    user_data = session.get('user_data')
    
    if not logged_in or not user_data or not user_data.get('db_id'):
        return jsonify({"success": False, "message": "Authentication required."}), 401
    
    user_id = user_data.get('db_id')
    
    data = request.get_json()
    try:
        song_id = int(data.get('song_id'))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid song ID."}), 400
        
    action = data.get('action') # 'add' or 'remove'
    
    if action not in ['add', 'remove']:
        return jsonify({"success": False, "message": "Invalid action."}), 400

    # Call the user_tracker function
    success, message = user_tracker.toggle_follow_status(user_id, song_id, action)
    
    return jsonify({"success": success, "message": message})

if __name__ == '__main__':
    #recorder.start()          # Start background radio recording
    #start_recorder()
    print(">>> Recorder Started <<<")
    app.run(debug=True)
