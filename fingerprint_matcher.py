# fingerprint_matcher.py
from dejavu import Dejavu
from dejavu.logic.recognizer.file_recognizer import FileRecognizer
import mysql.connector


class FingerprintMatcher:
    def __init__(self, mysql_config):
        self.mysql_config = mysql_config

        # Configure Dejavu
        config = {
            "database": {
                "host": mysql_config["host"],
                "user": mysql_config["user"],
                "password": mysql_config["password"],
                "database": mysql_config["database"],
            }
        }

        self.djv = None

    def recognize_clip(self, audio_path, stream_link):
        print(f"[Matcher] 🔍 Checking fingerprint for: {audio_path}")

        try:
            result = self.djv.recognize(FileRecognizer, audio_path)

            if not result or "song_id" not in result:
                print(f"[Matcher] ❌ No match found for stream → {stream_link}")
                return None

            song_id = result["song_id"]

            print(f"[Matcher] 🎵 MATCH FOUND → Stream: {stream_link}, Song ID: {song_id}")
            return song_id

        except Exception as e:
            print(f"[Matcher] ❌ Fingerprint error for {stream_link}: {e}")
            return None
