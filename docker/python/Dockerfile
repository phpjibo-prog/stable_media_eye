FROM python:3.7

# 2. Install System Dependencies (Crucial for PyAudio, psycopg2, and pydub/ffmpeg)
# 'portaudio19-dev' and 'libasound-dev' are REQUIRED to compile PyAudio.
# 'libpq-dev' is highly recommended for psycopg2 installation.
# 'ffmpeg' is necessary for pydub to handle audio files.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libasound-dev \
    libpq-dev \
    ffmpeg \
    gcc \
    build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. Set Working Directory and Copy Requirements
WORKDIR /app
COPY requirements.txt .

# 4. Install Python Dependencies
# PyAudio is included here from your requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy Application Code
COPY . .

# 6. Define the Start Command (Crucial for successful runtime)
# Replace 'app:app' with the correct MODULE:OBJECT for your application 
# (e.g., multi_stream_recorder:app if your app object is named 'app' inside multi_stream_recorder.py)
CMD gunicorn --bind 0.0.0.0:$PORT app:app
