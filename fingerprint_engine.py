# fingerprint_engine.py

import os
from dejavu import Dejavu
from dejavu.logic.recognizer.file_recognizer import FileRecognizer


class FingerprintEngine:
    def __init__(self, db_host="127.0.0.1", db_user="root", db_password="", db_name="media_daily_eye_db", db_port=3306):
        """
        Initialize Dejavu with DB config
        """
        self.config = {
            "database": {
                "host": db_host,
                "user": db_user,
                "password": db_password,
                "database": db_name,
                "port": int(db_port)  # 2. ADD THE PORT KEY HERE
            }
        }

        self.djv = None

    def fingerprint_folder(self, folder_path, extensions=[".mp3"], workers=3):
        """
        Fingerprint all audio files in a directory
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        print(f"[FINGERPRINT] Starting fingerprinting for: {folder_path}")
        self.djv.fingerprint_directory(folder_path, extensions, workers)
        print("[FINGERPRINT] Completed.")

    def fingerprint_file(self, file_path):
        """
        Fingerprint a single audio file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        print(f"[FINGERPRINT] Fingerprinting file: {file_path}")
        #self.djv.fingerprint_file(file_path)
        self.djv.fingerprint_directory("uploads", [".mp3"], 3)
        print("[FINGERPRINT] Completed.")

    def recognize_file(self, file_path):
        """
        Recognize audio fingerprint in a file
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        print(f"[RECOGNIZE] Recognizing audio from: {file_path}")
        result = self.djv.recognize(FileRecognizer, file_path)
        print("[RECOGNIZE] Result:", result)
        return result
