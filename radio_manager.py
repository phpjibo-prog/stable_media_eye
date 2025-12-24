# radio_manager.py

import mysql.connector
from mysql.connector import Error

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

    # radio_manager.py (Modified get_all_radios method)

    def get_all_radios(self):
        """
        Fetches all radio station records from the 'radios' table,
        including the icon path, radio name, stream link, and region name
        (aliased from country_name) for display and playback.
        """
        conn = self.get_db_connection()
        radios_data = []

        if not conn:
            return radios_data

        cursor = conn.cursor(dictionary=True)

        try:
            # MODIFIED: Included 'stream_link' and used an alias for 'region_name'
            cursor.execute("""
                SELECT 
                    radio_id, 
                    radio_name, 
                    country_name AS region_name, -- Alias 'country_name' to 'region_name' for display
                    icon_path,
                    stream_link                     -- New column for playback
                FROM radios
                ORDER BY radio_name
            """)
            radios_data = cursor.fetchall()
        
        except Error as e:
            print(f"Database error fetching radios: {e}")

        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
        return radios_data