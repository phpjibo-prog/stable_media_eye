# radio_manager.py

import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta # Import necessary modules

class RadioManager:
    """
    Handles operations related to radio stations, primarily fetching data
    for display.
    """
    def __init__(self, db_config):
        self.db_config = db_config

    def get_db_connection(self):
        """Establishes a new database connection."""
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except Error as e:
            # In a real app, use proper logging here
            print(f"Error connecting to MySQL from RadioManager: {e}")
            return None

    def get_total_songs_count(self):
        """Fetches the total number of songs recorded in the 'songs' table."""
        conn = self.get_db_connection()
        if not conn:
            return 0

        cursor = conn.cursor()
        count = 0
        try:
            # Query to count all records in the songs table
            cursor.execute("SELECT COUNT(song_id) FROM songs")
            # Fetch the first (and only) result
            count = cursor.fetchone()[0]
        except Error as e:
            print(f"Database error fetching song count: {e}")
            count = 0
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
        return count

    # REVISED FUNCTION: Calculate played songs count with de-duplication and date range filtering
    def get_played_count_for_radio(self, stream_link, start_date=None, end_date=None):
        """
        Calculates the number of unique song plays for a given radio stream_link 
        within a specified date range. Plays of the same song_id within a 10-minute 
        window are counted as one.
        
        :param stream_link: The URL of the radio stream.
        :param start_date: datetime object for the start of the filter window.
        :param end_date: datetime object for the end of the filter window.
        """
        conn = self.get_db_connection()
        if not conn:
            return 0
        
        cursor = conn.cursor()
        play_count = 0
        
        # 1. Build the base query and parameters
        query = """
            SELECT 
                song_id, 
                played_time
            FROM audio_played
            WHERE stream_url = %s
        """
        params = [stream_link]
        
        # 2. Add date filtering conditions
        if start_date:
            query += " AND played_time >= %s"
            params.append(start_date)
            
        if end_date:
            query += " AND played_time <= %s"
            params.append(end_date)
            
        query += " ORDER BY played_time"
        
        try:
            # Execute the query with date range filtering
            cursor.execute(query, tuple(params))
            
            plays = cursor.fetchall()

            if not plays:
                return 0
            
            # 3. Manual de-duplication logic (10-minute window)
            current_song_id = None
            last_played_at = None
            
            for song_id, played_time in plays:
                if song_id is None:
                    continue # Skip plays with no matching song
                
                # Check if this is a new song or the same song outside the 10-minute window (600 seconds)
                if song_id != current_song_id or \
                   (last_played_at and (played_time - last_played_at).total_seconds() > 600):
                    
                    play_count += 1
                    current_song_id = song_id
                    
                last_played_at = played_time
            
        except Error as e:
            print(f"Database error calculating play count: {e}")
            play_count = 0
            
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
        return play_count


    # radio_manager.py (Modified get_all_radios method)
    # radio_manager.py (Excerpt)
# ... imports and get_db_connection remain the same ...

    # radio_manager.py (Modified get_all_radios method)
    def get_all_radios(self, start_date=None, end_date=None):
        """
        Fetches all radio station records and calculates the 'played_count'.
        Accepts optional start and end dates for filtering.
        """
        conn = self.get_db_connection()
        radios_data = []

        if not conn:
            return radios_data

        cursor = conn.cursor(dictionary=True)
        
        # Determine the filter window (7-day default if no dates are passed)
        if not start_date or not end_date:
            filter_end = datetime.now()
            filter_start = filter_end - timedelta(days=7)
        else:
            filter_start = start_date
            filter_end = end_date

        try:
            # Fetch radio station details (Query remains the same)
            cursor.execute("""
                SELECT 
                    radio_id, 
                    radio_name, 
                    country_name,
                    region_name,
                    icon_path,
                    stream_link
                FROM radios
                ORDER BY radio_name
            """)
            
            raw_radios_data = cursor.fetchall()
            
            # Add the played_count to each radio dict using the determined filter
            for radio in raw_radios_data:
                radio['played_count'] = self.get_played_count_for_radio(
                    radio['stream_link'],
                    start_date=filter_start, # Pass the calculated filter dates
                    end_date=filter_end      # Pass the calculated filter dates
                )
                radios_data.append(radio)
        
        except Error as e:
            print(f"Database error fetching radios: {e}")

        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
        return radios_data
