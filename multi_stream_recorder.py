import os
import time
import threading
import subprocess
from datetime import datetime
import mysql.connector
import subprocess
from fingerprint_matcher import FingerprintMatcher

class MultiStreamRecorder:
    def __init__(self,
                 mysql_config,
                 output_folder="recordings", # <-- CHANGED FOLDER NAME HERE
                 record_seconds=5,
                 wait_seconds=10):

        self.mysql_config = mysql_config
        self.output_folder = output_folder
        self.record_seconds = record_seconds
        self.wait_seconds = wait_seconds
        self.matcher = None

        self._stop_event = threading.Event()

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

    # ---------------------------------------------------
    # Fetch streams from MySQL
    # ---------------------------------------------------
    def load_streams_from_db(self):
        conn = mysql.connector.connect(**self.mysql_config)
        cursor = conn.cursor()

        cursor.execute("SELECT stream_link FROM radios")
        rows = cursor.fetchall()

        streams = [row[0] for row in rows]

        cursor.close()
        conn.close()

        print(f"[DB] Loaded {len(streams)} radio streams.")
        return streams

    # ---------------------------------------------------
    def start(self):
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print("[Recorder] Background recorder started.")

    def stop(self):
        self._stop_event.set()
        print("[Recorder] Recorder stopped.")

    # ---------------------------------------------------
    def _loop(self):

        while not self._stop_event.is_set():

            streams = self.load_streams_from_db()

            print("[Recorder] Starting recording cycle...")

            threads = []
            for idx, stream in enumerate(streams):
                t = threading.Thread(
                    target=self._record_single,
                    args=(idx, stream)
                )
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            print(f"[Recorder] Sleeping {self.wait_seconds} sec...")
            time.sleep(self.wait_seconds)

    # ---------------------------------------------------
    def audio_has_duration(self, filepath):
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            duration = float(proc.stdout.decode().strip())
            time.sleep(0.05) # Added delay to release file handle (as per previous fix)
            return duration > 0.1   # more than 0.1 sec audio
        except:
            time.sleep(0.05) # Added delay to release file handle
            return False
    
    def log_error_to_db(self, stream_link, error_message):
        try:
            conn = mysql.connector.connect(**self.mysql_config)
            cursor = conn.cursor()

            sql = """
                INSERT INTO recorder_error (stream_link, error_time, error_message)
                VALUES (%s, NOW(), %s)
            """
            cursor.execute(sql, (stream_link, error_message))

            conn.commit()
            cursor.close()
            conn.close()

            print(f"[DB] Error logged for stream: {stream_link}")

        except Exception as e:
            print(f"[DB] Failed to log error: {e}")

    def log_audio_played(self, song_id, stream_url):
        try:
            conn = mysql.connector.connect(**self.mysql_config)
            cursor = conn.cursor()

            sql = """
                INSERT INTO audio_played (song_id, stream_url, matched)
                VALUES (%s, %s, 1)
            """

            cursor.execute(sql, (song_id, stream_url))
            conn.commit()

            cursor.close()
            conn.close()

            print(f"[DB] ✔ Logged played audio → Song {song_id}, Stream {stream_url}")

        except Exception as e:
            print(f"[DB] ❌ Failed to log audio_played: {e}")


    def _record_single(self, idx, url):
        matcher = self._get_matcher()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"radio_{idx}_{timestamp}.mp3"
        path = os.path.join(self.output_folder, filename)

        print(f"[Recorder] Recording {url} → {filename}")

        cmd = [
            "ffmpeg",
            "-y",
            "-i", url,
            "-t", str(self.record_seconds),
            "-vn",
            "-acodec", "libmp3lame",
            path
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[Recorder] Saved {path}")
            
            if self.audio_has_duration(path):
                print(f"[Recorder] ✅ Audio OK: {path}")
                
                # --- MATCHING & LOGGING ---
                song_id = self.matcher.recognize_clip(path, url)

                if song_id:
                    print(f"[Recorder] 🎯 MATCH → Stream: {url}, Song ID: {song_id}")
                    self.log_audio_played(song_id, url)
                else:
                    print(f"[Recorder] ❌ No match for stream: {url}")
                    self.log_audio_played(song_id, url)
                # --------------------------

            else:
                print(f"[Recorder] ❌ EMPTY CLIP: {path}")
                self.log_error_to_db(url, "EMPTY CLIP")
            
            # --- FILE DELETION LOGIC (Cleanup) ---
            if os.path.exists(path):
                os.remove(path)
                print(f"[Recorder] 🗑️ DELETED CLIP: {path}")
            # -------------------------------------

        except Exception as e:
            print(f"[Recorder] ERROR {url}: {e}")
            # --- FILE DELETION LOGIC (Cleanup after error) ---
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[Recorder] 🗑️ DELETED CLIP after ERROR: {path}")
                except Exception as del_e:
                    print(f"[Recorder] ⚠️ Failed to delete file {path} after error: {del_e}")
            # -------------------------------------------------
