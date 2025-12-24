# user_tracker.py

import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta

class UserTracker:
    """
    Handles operations related to user's tracked songs (My List), 
    including fetching song details and calculating play counts.
    """
    def __init__(self, db_config):
        self.db_config = db_config

    def get_db_connection(self):
        """Establishes a new database connection."""
        try:
            conn = mysql.connector.connect(**self.db_config)
            return conn
        except Error as e:
            print(f"Error connecting to MySQL from UserTracker: {e}")
            return None

    def get_user_tracked_plays(self, user_id, start_date=None, end_date=None):
        """
        Fetches the play count for each of the user's followed songs 
        across various radio streams within the specified date range.

        :param user_id: The ID of the logged-in user.
        :param start_date: datetime object for the start of the filter window.
        :param end_date: datetime object for the end of the filter window.
        :return: A list of dicts: 
                 [{'song_name': str, 'radios': [{'radio_name': str, 'icon_path': str, 'count': int}, ...]}, ...]
        """
        conn = self.get_db_connection()
        if not conn:
            return []

        # --- 1. Set Default Date Range ---
        if not start_date or not end_date:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

        # --- 2. Fetch User Follows Data ---
        # Get all followed songs, preferring custom_name over song_name.
        # We assume 'user_tracks' is actually the 'songs' table.
        query_follows = """
            SELECT 
                uf.song_id AS track_id, 
                COALESCE(uf.custom_name, s.song_name) AS track_name
            FROM user_follows uf
            LEFT JOIN songs s ON uf.song_id = s.song_id
            WHERE uf.user_id = %s
        """
        user_follows = {} # {track_id: track_name, ...}
        
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_follows, (user_id,))
            
            for row in cursor.fetchall():
                user_follows[row['track_id']] = row['track_name']
            
        except Error as e:
            print(f"Database error fetching user follows: {e}")
            return []
        finally:
            cursor.close()

        if not user_follows:
            return []

        # --- 3. Fetch all relevant audio_played data for de-duplication ---
        # Get all plays for all followed songs within the date range.
        followed_track_ids = tuple(user_follows.keys())
        
        # Ensure the list of IDs is not empty for the SQL IN clause
        if not followed_track_ids:
             return []

        # The '%s' placeholder handles both single and multiple track_ids
        track_ids_placeholder = ', '.join(['%s'] * len(followed_track_ids))
        
        query_plays = f"""
            SELECT 
                ap.song_id AS track_id, 
                ap.stream_url, 
                ap.played_time,
                r.radio_name,
                r.icon_path
            FROM audio_played ap
            JOIN radios r ON ap.stream_url = r.stream_link
            WHERE ap.song_id IN ({track_ids_placeholder})
            AND ap.played_time >= %s
            AND ap.played_time <= %s
            ORDER BY ap.song_id, ap.stream_url, ap.played_time
        """
        
        params = list(followed_track_ids) + [start_date, end_date]
        
        all_plays = []
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_plays, tuple(params))
            all_plays = cursor.fetchall()
        except Error as e:
            print(f"Database error fetching audio plays: {e}")
            return []
        finally:
            cursor.close()
            conn.close()


        # --- 4. Process Data: De-duplication and Aggregation ---
        
        # Structure to hold final results:
        # {track_id: {'track_name': str, 'radios': {stream_url: {'radio_name': str, 'icon_path': str, 'count': int}, ...}}}
        results_map = {
            track_id: {'track_name': name, 'radios': {}}
            for track_id, name in user_follows.items()
        }

        # De-duplication Logic (10-minute window)
        current_track_id = None
        current_stream_url = None
        last_played_at = None

        for play in all_plays:
            track_id = play['track_id']
            stream_url = play['stream_url']
            played_time = play['played_time']

            # Initialize the radio data structure if it doesn't exist
            if stream_url not in results_map[track_id]['radios']:
                results_map[track_id]['radios'][stream_url] = {
                    'radio_name': play['radio_name'],
                    'icon_path': play['icon_path'],
                    'count': 0
                }

            # Check for 10-minute de-duplication
            # If it's a new track, a new stream, or 10+ minutes passed since the last play of this specific track/stream combo
            if track_id != current_track_id or \
               stream_url != current_stream_url or \
               (last_played_at and (played_time - last_played_at).total_seconds() > 600): # 600 seconds = 10 minutes
                
                results_map[track_id]['radios'][stream_url]['count'] += 1
                
                current_track_id = track_id
                current_stream_url = stream_url
            
            last_played_at = played_time

        # --- 5. Format Output ---
        final_list = []
        for track_data in results_map.values():
            # Convert the 'radios' dict of dicts to a list of dicts for easier use in Jinja
            track_data['radios'] = list(track_data['radios'].values())
            # Remove radios with zero counts after de-duplication
            track_data['radios'] = [r for r in track_data['radios'] if r['count'] > 0]
            
            # Only include songs that actually had plays
            if track_data['radios']:
                final_list.append(track_data)
                
        return final_list
    
    def get_most_played_tracks(self, user_id=None, start_date=None, end_date=None):
        """
        Calculates the most played songs overall (if not logged in) or for the 
        logged-in user's followed songs, sorted by total play count.

        This function fully addresses:
        1. Date range filtering (7 days default or calendar selection).
        2. Conditional song selection (user_follows/custom_name if logged in, all songs if not).
        3. 10-minute play de-duplication per stream_url.
        4. Join with radios table for icon and name.
        5. Sorting by total play count.
        """
        conn = self.get_db_connection()
        if not conn:
            return []

        # --- 1. Set Default Date Range ---
        if not start_date or not end_date:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

        # --- 2. Determine the set of Track IDs and their Names ---
        track_map = {} # {track_id: track_name}
        
        try:
            cursor = conn.cursor(dictionary=True)
            
            if user_id:
                # Logged In: Get songs from user_follows (with custom_name/song_name resolution)
                # Assumes user_tracks refers to the songs table.
                query_tracks = """
                    SELECT 
                        uf.song_id, 
                        COALESCE(uf.custom_name, s.song_name) AS track_name
                    FROM user_follows uf
                    LEFT JOIN songs s ON uf.song_id = s.song_id
                    WHERE uf.user_id = %s
                """
                cursor.execute(query_tracks, (user_id,))
            else:
                # Not Logged In: Get ALL songs from the songs table
                query_tracks = "SELECT song_id, song_name AS track_name FROM songs"
                cursor.execute(query_tracks)

            for row in cursor.fetchall():
                if row['song_id'] and row['track_name']:
                    track_map[row['song_id']] = row['track_name']
                
        except Error as e:
            print(f"Database error determining track set: {e}")
            return []
        finally:
            cursor.close()

        if not track_map:
            return []

        # --- 3. Fetch all relevant audio_played data for de-duplication ---
        followed_track_ids = tuple(track_map.keys())
        track_ids_placeholder = ', '.join(['%s'] * len(followed_track_ids))

        query_plays = f"""
            SELECT 
                ap.song_id AS track_id, 
                ap.stream_url, 
                ap.played_time,
                r.radio_name,
                r.icon_path
            FROM audio_played ap
            JOIN radios r ON ap.stream_url = r.stream_link
            WHERE ap.song_id IN ({track_ids_placeholder})
            AND ap.played_time >= %s
            AND ap.played_time <= %s
            ORDER BY ap.song_id, ap.stream_url, ap.played_time
        """
        
        params = list(followed_track_ids) + [start_date, end_date]
        
        all_plays = []
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query_plays, tuple(params))
            all_plays = cursor.fetchall()
        except Error as e:
            print(f"Database error fetching audio plays: {e}")
            return []
        finally:
            cursor.close()
            conn.close()

        # --- 4. Process Data: De-duplication and Aggregation ---
        results_map = {
            track_id: {'track_name': name, 'total_count': 0, 'radios': {}}
            for track_id, name in track_map.items()
        }

        current_track_id = None
        current_stream_url = None
        last_played_at = None

        for play in all_plays:
            track_id = play['track_id']
            stream_url = play['stream_url']
            played_time = play['played_time']

            if stream_url not in results_map[track_id]['radios']:
                results_map[track_id]['radios'][stream_url] = {
                    'radio_name': play['radio_name'],
                    'icon_path': play['icon_path'],
                    'count': 0
                }

            # 10-minute de-duplication logic
            if track_id != current_track_id or \
               stream_url != current_stream_url or \
               (last_played_at and (played_time - last_played_at).total_seconds() > 600):
                
                results_map[track_id]['radios'][stream_url]['count'] += 1
                results_map[track_id]['total_count'] += 1
                
                current_track_id = track_id
                current_stream_url = stream_url
            
            last_played_at = played_time

        # --- 5. Format and Sort Output ---
        final_list = []
        for track_data in results_map.values():
            if track_data['total_count'] > 0:
                # Convert the 'radios' dict to a list of non-zero count entries
                track_data['radios'] = [r for r in track_data['radios'].values() if r['count'] > 0]
                final_list.append(track_data)
                
        # Sort by total_count descending
        final_list.sort(key=lambda x: x['total_count'], reverse=True)
                
        return final_list
    
    def get_all_songs_with_status(self, user_id):
        """
        Fetches all songs and checks if the given user is currently following each one.
        :param user_id: The ID of the logged-in user.
        :return: List of songs with an 'is_followed' boolean status.
        """
        conn = self.get_db_connection()
        if not conn:
            return []

        # Join songs with user_follows only for the current user (LEFT JOIN)
        # We assume 'user_tracks' refers to the 'songs' table.
        query = """
            SELECT 
                s.song_id, 
                s.song_name AS track_name,
                uf.id IS NOT NULL AS is_followed
            FROM songs s
            LEFT JOIN user_follows uf 
                ON s.song_id = uf.song_id AND uf.user_id = %s
            ORDER BY s.song_name
        """
        
        songs_list = []
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, (user_id,))
            songs_list = cursor.fetchall()
        except Error as e:
            print(f"Database error fetching all songs with follow status: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
        return songs_list

    def toggle_follow_status(self, user_id, song_id, action):
        """
        Adds a song to user_follows or deletes it based on the action.
        :param action: 'add' or 'remove'
        :return: (success: bool, message: str)
        """
        conn = self.get_db_connection()
        if not conn:
            return False, "Database connection failed."

        try:
            cursor = conn.cursor()
            
            if action == 'add':
                # ADD: Insert row for new follow
                # Note: custom_name is optional and left NULL by default
                query = "INSERT INTO user_follows (user_id, song_id, followed_at) VALUES (%s, %s, NOW())"
                cursor.execute(query, (user_id, song_id))
                conn.commit()
                return True, "Song followed successfully."
                
            elif action == 'remove':
                # REMOVE: Delete the follow row
                query = "DELETE FROM user_follows WHERE user_id = %s AND song_id = %s"
                cursor.execute(query, (user_id, song_id))
                conn.commit()
                if cursor.rowcount > 0:
                    return True, "Song unfollowed successfully."
                else:
                    return False, "Song was not found in your list."

            else:
                return False, "Invalid action specified."

        except Error as e:
            conn.rollback()
            print(f"Database error during follow/unfollow: {e}")
            return False, f"Database error: {e}"
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
