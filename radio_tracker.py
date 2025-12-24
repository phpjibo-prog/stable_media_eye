# radio_tracker.py

import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta

class RadioPlayTracker:
    """
    Manages fetching and processing radio play statistics from the database.
    Applies a 10-minute de-duplication rule for consecutive plays on the same stream.
    """
    def __init__(self, db_config):
        self.db_config = db_config

    def get_db_connection(self):
        """Establishes a new database connection."""
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except Error as e:
            print(f"Error connecting to MySQL from RadioPlayTracker: {e}")
            return None

    def _get_start_date(self, time_range_key):
        """Calculates the start datetime for filtering based on the range key (day, week, month)."""
        now = datetime.now()
        
        if time_range_key == 'day':
            # Start of today
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif time_range_key == 'month':
            # Start of the current month
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else: # Default is 'week'
            # Start of the week (assuming Monday is the start, weekday() is 0 for Monday)
            start_of_week = now - timedelta(days=now.weekday())
            start_date = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
            
        return start_date

    def get_radio_play_stats(self, time_range_key='week'):
        """
        Fetches radio play statistics within the specified time range and
        applies the 10-minute de-duplication rule.
        """
        start_date = self._get_start_date(time_range_key)
        
        conn = self.get_db_connection()
        if not conn:
            return []
        
        cursor = conn.cursor(dictionary=True)
        radio_stats = []

        try:
            # SQL query to get all matched played audio within the time range,
            # along with the radio's name and icon path, sorted by stream and time for de-duplication.
            sql_query = """
                SELECT 
                    ap.stream_url,
                    ap.played_time,
                    r.radio_name,
                    r.icon_path
                FROM 
                    audio_played ap
                JOIN 
                    radios r ON ap.stream_url = r.stream_link
                WHERE 
                    ap.matched = 1 AND ap.played_time >= %s
                ORDER BY 
                    ap.stream_url, ap.played_time ASC
            """
            cursor.execute(sql_query, (start_date,))
            all_plays = cursor.fetchall()

            # --- Python-side De-duplication Logic (10-minute interval rule) ---
            grouped_plays = {}
            for row in all_plays:
                url = row['stream_url']
                
                if url not in grouped_plays:
                    grouped_plays[url] = {
                        'radio_name': row['radio_name'],
                        'icon_path': row['icon_path'],
                        'play_count': 0,
                        'last_counted_time': None
                    }
                
                play_time = row['played_time']
                last_time = grouped_plays[url]['last_counted_time']
                
                # Check if the current play is at least 10 minutes (600 seconds) after the last counted play.
                if last_time is None or (play_time - last_time).total_seconds() >= 600:
                    grouped_plays[url]['play_count'] += 1
                    grouped_plays[url]['last_counted_time'] = play_time

            # Format the final output
            for data in grouped_plays.values():
                radio_stats.append({
                    'radio_name': data['radio_name'],
                    'icon_path': data['icon_path'],
                    'times_played': data['play_count']
                })

        except Error as e:
            print(f"Error executing query in RadioPlayTracker: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
        return radio_stats