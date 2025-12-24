import json
from dejavu import Dejavu
from dejavu.logic.recognizer.file_recognizer import FileRecognizer

with open("dejavu.cnf") as f:
    config = json.load(f)

djv = Dejavu(config)

result = djv.recognize(FileRecognizer, "audio/Big Sean - Deep Reverence (Official Music Video) ft. Nipsey Hussle.mp3")
print("Recognition result:", result)