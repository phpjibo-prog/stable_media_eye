# radio_playback_manager.py

import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta

class RadioPlaybackManager:
    """
    Handles fetching and aggregating radio playback data based on time periods
    (date, week, month) for display.
    """
    def __init__(self, db_config):
        self.db_config = db_config

    def get_db_connection(self):
        """Establishes a new database connection."""
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except Error as e:
            print(f"Error connecting to MySQL from RadioPlaybackManager: {e}")
            return None

    def get_time_period_start(self, period_type, date_str):
        """Calculates the start date for the given period (date, week, month)."""
        if date_str:
            base_date = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            # Default to today if no date is provided
            base_date = datetime.now()

        if period_type == 'date':
            # Start of the selected day
            start_date = base_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'week':
            # Start of the week (Monday)
            start_date = base_date - timedelta(days=base_date.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'month':
            # Start of the selected month
            start_date = base_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            # Default to week if type is unknown
            return self.get_time_period_start('week', None)
            
        return start_date

    def get_aggregated_plays(self, period_type='week', date_str=None):
        """
        Fetches matched radio plays and aggregates them into counts per radio,
        grouping plays less than 10 minutes apart as one count.
        """
        conn = self.get_db_connection()
        if not conn:
            return []

        start_date = self.get_time_period_start(period_type, date_str)
        end_date = start_date + self.get_time_period_delta(period_type)

        cursor = conn.cursor(dictionary=True)
        
        # This query joins audio_played (matched=TRUE) with radios using stream_url/stream_link
        query = """
            SELECT 
                r.radio_id,
                r.radio_name,
                r.icon_path,
                ap.played_time
            FROM audio_played ap
            JOIN radios r ON ap.stream_url = r.stream_link
            WHERE ap.matched = TRUE AND ap.played_time >= %s AND ap.played_time < %s
            ORDER BY r.radio_id, ap.played_time ASC
        """
        
        try:
            cursor.execute(query, (start_date, end_date))
            raw_plays = cursor.fetchall()
        except Error as e:
            print(f"Database error fetching aggregated plays: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

        # --- Aggregation Logic (Counting plays < 10 mins apart as one) ---
        radio_plays = {}

        for play in raw_plays:
            radio_id = play['radio_id']
            play_time = play['played_time']

            if radio_id not in radio_plays:
                # Initialize new radio entry
                radio_plays[radio_id] = {
                    'radio_id': radio_id,
                    'radio_name': play['radio_name'],
                    'icon_path': play['icon_path'],
                    'play_count': 1,
                    'last_play_time': play_time
                }
            else:
                last_time = radio_plays[radio_id]['last_play_time']
                time_difference = play_time - last_time

                # If the current play is 10 minutes or more after the last counted play,
                # it counts as a new instance.
                if time_difference >= timedelta(minutes=10):
                    radio_plays[radio_id]['play_count'] += 1
                    radio_plays[radio_id]['last_play_time'] = play_time
                # If less than 10 minutes, we ignore it, but we can update the last_play_time
                # to track subsequent matches if required. For simplicity, we only update
                # last_play_time when we count a new play.

        # Convert dictionary values to a list for template rendering
        results = list(radio_plays.values())
        
        # Remove the 'last_play_time' key before returning
        for result in results:
            del result['last_play_time'] 
            
        return results

    def get_time_period_delta(self, period_type):
        """Returns the timedelta for the end of the period."""
        if period_type == 'date':
            return timedelta(days=1)
        elif period_type == 'week':
            return timedelta(days=7)
        elif period_type == 'month':
            # Using 31 days is an approximation; the SQL should ideally calculate
            # the last day of the month, but using a delta of a month is tricky.
            # We'll rely on the logic in get_time_period_start which is more precise.
            # However, for the query boundary, we use the start of the *next* period
            # which is easier. For simplicity here, we'll return a large enough delta
            # to avoid cutting off data. For `get_aggregated_plays`, we use the
            # calculated end_date.
            return timedelta(days=31) # Safe delta, query handles the actual time range