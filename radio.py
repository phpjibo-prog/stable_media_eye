import ffmpeg
import os

# --- Configuration ---
stream_url = "http://eu6.fastcast4u.com:5306"  # Replace with your radio stream URL
output_folder = "recordings"
output_file = "radio_clip.mp3"
record_duration_seconds = 4

# Create output folder if it doesn't exist
os.makedirs(output_folder, exist_ok=True)

# Full path for output
save_path = os.path.join(output_folder, output_file)

# Record exactly 4 seconds using ffmpeg
(
    ffmpeg
    .input(stream_url, t=record_duration_seconds)  # 't' specifies duration in seconds
    .output(save_path, format='mp3', acodec='mp3')
    .run(overwrite_output=True)
)

print(f"Saved {record_duration_seconds}-second recording to {save_path}")