import json
import os
from dejavu import Dejavu

if __name__ == "__main__":
    from dejavu import Dejavu
    config = {
        "database": {
            "host": "127.0.0.1",
            "user": "root",
            "password": "", 
            "database": "media_daily_eye_db",
        }
    }
    djv = Dejavu(config)

    djv.fingerprint_directory("audio", [".mp3"], 3)