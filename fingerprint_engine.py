# fingerprint_engine.py

import os
from dejavu import Dejavu
from dejavu.logic.recognizer.file_recognizer import FileRecognizer


class FingerprintEngine:
    def __init__(self, db_host= os.environ.get('MYSQLHOST', ''), db_user= os.environ.get('MYSQLUSER', ''), db_password= os.environ.get('MYSQLPASSWORD', ''), db_name= os.environ.get('MYSQLDATABASE', ''), db_port= os.environ.get('MYSQLPORT', 3306)):
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

        self.djv = Dejavu(self.config)

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
        print("reched fingerprint file")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        abs_path = os.path.abspath(file_path)
        folder = os.path.dirname(abs_path)
        song_name = os.path.splitext(os.path.basename(file_path))[0]
        print(song_name)
        print(f"[FINGERPRINT] Processing: {abs_path}")
        print(f"[FINGERPRINT] Processing folder: {folder}")
        print(f"[FINGERPRINT] Fingerprinting file: {file_path}")
        
        try:
            # Try passing song_name explicitly if your version requires it
            self.djv.fingerprint_directory(folder, [".mp3"], nprocesses=1)
            print("[FINGERPRINT] Successfully completed on Railway.")
        except TypeError:
            # If it still fails with the same error, use the directory method 
            # pointed at the specific file's folder
            folder = os.path.dirname(file_path)
            self.djv.fingerprint_directory(folder, [".mp3"], 1)
        
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
