# worker.py
import os
import time
from multi_stream_recorder import MultiStreamRecorder
from fingerprint_engine import FingerprintEngine
from youtube_downloader import download_youtube_as_mp3
import mysql.connector

# Database Configuration from environment variables
DB_CONFIG = {
    'host': os.environ.get('MYSQLHOST', ''),
    'user': os.environ.get('MYSQLUSER', ''),
    'password': os.environ.get('MYSQLPASSWORD', ''),
    'database': os.environ.get('MYSQLDATABASE', ''), 
    'port': int(os.environ.get('MYSQLPORT', 3306))
}

def main():
    print("--- Starting Background Audio Worker ---")
    
    # Initialize the recorder
    #recorder = MultiStreamRecorder(DB_CONFIG)
    
    # Ensure FingerprintEngine uses the DB_CONFIG properly
    f_engine = FingerprintEngine(
        db_host=DB_CONFIG['host'],
        db_user=DB_CONFIG['user'],
        db_password=DB_CONFIG['password'],
        db_name=DB_CONFIG['database'],
        db_port=DB_CONFIG['port']
    )

    # Start the recorder in a separate thread/background
    #recorder.start()

    temp_folder = os.path.join(os.getcwd(), 'temp')
    os.makedirs(temp_folder, exist_ok=True)

    while True:
        conn = None
        local_path = None
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)

            # Look for tracks waiting to be downloaded
            cursor.execute("SELECT track_id, file_path FROM user_tracks WHERE status = 'pending_download' LIMIT 1")
            job = cursor.fetchone()

            if job:
                track_id = job['track_id']
                url = job['file_path'] # The URL we saved in app.py

                print(f"[WORKER] Starting download for URL: {url}")
                try:
                    # 1. DOWNLOAD
                    track_name, local_path = download_youtube_as_mp3(url, temp_folder)
                    abs_path = os.path.abspath(local_path)
                    
                    # 2. FINGERPRINT
                    print(f"[WORKER] Downloading finished. Fingerprinting: {track_name}")
                    f_engine.fingerprint_file(abs_path)

                    # 3. UPDATE DB
                    cursor.execute("""UPDATE user_tracks SET 
                                      track_name = %s, 
                                      file_path = %s, 
                                      status = 'completed' 
                                      WHERE track_id = %s""", 
                                   (track_name, abs_path, track_id))
                    print(f"[WORKER] Success: {track_name}")

                except Exception as download_err:
                    print(f"[WORKER] Download/Fingerprint failed: {download_err}")
                    cursor.execute("UPDATE user_tracks SET status = 'failed' WHERE track_id = %s", (track_id,))
                
                conn.commit()

            cursor.close()
        except Exception as e:
            print(f"[WORKER ERROR]: {e}")
        finally:
            if conn and conn.is_connected():
                conn.close()

            if local_path and os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                            print(f"[WORKER] Deleted temporary file: {local_path}")
                        except Exception as e:
                            print(f"[WORKER] Cleanup Error: {e}")

        time.sleep(10)
if __name__ == '__main__':
    main()
