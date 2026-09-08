"""
Storage layer for Daily Check-In application.
Supports Supabase, Google Sheets (st-gsheets-connection), and local SQLite fallback.
Includes photo upload handling and optimization for mobile capture.
"""

from abc import ABC, abstractmethod
import datetime
import os
import sqlite3
from typing import Optional, List, Dict, Any
import uuid
from PIL import Image, ImageOps
import streamlit as st


def save_uploaded_photo(uploaded_file, upload_dir: str = "uploads") -> Optional[str]:
    """
    Optimizes and saves a mobile camera photo or gallery upload.
    Resizes image to max 800px dimension and saves as optimized JPEG.
    Returns relative path to saved image, or None if no file was uploaded.
    """
    if uploaded_file is None:
        return None
    try:
        os.makedirs(upload_dir, exist_ok=True)
        img = Image.open(uploaded_file)
        
        # Correct orientation from mobile EXIF data
        img = ImageOps.exif_transpose(img)
        
        # Convert RGBA/palette images to RGB for JPEG
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        # Downscale large mobile camera photos
        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{timestamp}_{uuid.uuid4().hex[:6]}.jpg"
        filepath = os.path.join(upload_dir, filename)
        
        img.save(filepath, format="JPEG", quality=80, optimize=True)
        return filepath
    except Exception as e:
        st.error(f"Error processing image: {e}")
        return None


class StorageBackend(ABC):
    backend_name: str = "Base"

    @abstractmethod
    def save_checkin(
        self,
        name: str,
        mood: str,
        note: str,
        photo_path: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """Save a new check-in entry."""
        pass

    @abstractmethod
    def get_recent_checkins(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent check-in entries ordered by date descending."""
        pass

    def get_latest_checkin(self) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent check-in entry."""
        recent = self.get_recent_checkins(limit=1)
        return recent[0] if recent else None


class SQLiteBackend(StorageBackend):
    backend_name = "Local SQLite"

    def __init__(self, db_path: str = "checkins.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS checkins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at TEXT NOT NULL,
                        name TEXT NOT NULL,
                        mood TEXT NOT NULL,
                        note TEXT,
                        photo_path TEXT
                    )
                    """
                )
                # Auto-migrate table if photo_path column was not present in earlier schema
                cursor.execute("PRAGMA table_info(checkins)")
                columns = [row[1] for row in cursor.fetchall()]
                if "photo_path" not in columns:
                    cursor.execute("ALTER TABLE checkins ADD COLUMN photo_path TEXT")
                conn.commit()
        except Exception as e:
            st.error(f"Database initialization error: {e}")

    def save_checkin(
        self,
        name: str,
        mood: str,
        note: str,
        photo_path: Optional[str] = None,
        **kwargs,
    ) -> bool:
        try:
            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO checkins (created_at, name, mood, note, photo_path)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (now_iso, name.strip(), mood, note.strip() if note else "", photo_path),
                )
                conn.commit()
            return True
        except Exception as e:
            st.error(f"Error saving to SQLite: {e}")
            return False

    def get_recent_checkins(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, created_at, name, mood, note, photo_path
                    FROM checkins
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            # Fallback if photo_path column is missing in legacy table
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT id, created_at, name, mood, note
                        FROM checkins
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    rows = cursor.fetchall()
                    data = [dict(row) for row in rows]
                    for r in data:
                        r["photo_path"] = None
                    return data
            except Exception:
                st.error(f"Error reading from SQLite: {e}")
                return []


class SupabaseBackend(StorageBackend):
    backend_name = "Supabase"

    def __init__(self, url: str, key: str, table_name: str = "checkins"):
        from supabase import create_client, Client
        self.table_name = table_name
        self.client: Client = create_client(url, key)

    def save_checkin(
        self,
        name: str,
        mood: str,
        note: str,
        photo_path: Optional[str] = None,
        **kwargs,
    ) -> bool:
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            payload = {
                "name": name.strip(),
                "mood": mood,
                "note": note.strip() if note else "",
                "created_at": now_iso,
            }
            if photo_path:
                payload["photo_path"] = photo_path

            try:
                res = self.client.table(self.table_name).insert(payload).execute()
            except Exception as e:
                # If Supabase table does not have photo_path column yet, fallback without it
                if "photo_path" in payload and "photo_path" in str(e):
                    payload.pop("photo_path")
                    res = self.client.table(self.table_name).insert(payload).execute()
                else:
                    raise e

            return bool(res.data)
        except Exception as e:
            st.error(f"Error saving to Supabase: {e}")
            return False

    def get_recent_checkins(self, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            try:
                res = (
                    self.client.table(self.table_name)
                    .select("id, created_at, name, mood, note, photo_path")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
                )
            except Exception as e:
                # Fallback if photo_path column does not exist in Supabase schema
                if "photo_path" in str(e):
                    res = (
                        self.client.table(self.table_name)
                        .select("id, created_at, name, mood, note")
                        .order("created_at", desc=True)
                        .limit(limit)
                        .execute()
                    )
                else:
                    raise e

            data = res.data or []
            # Format created_at to readable string if ISO timestamp
            for row in data:
                raw_time = row.get("created_at")
                if raw_time:
                    try:
                        dt = datetime.datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                        row["created_at"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass
                if "photo_path" not in row:
                    row["photo_path"] = None
            return data
        except Exception as e:
            st.error(f"Error reading from Supabase: {e}")
            return []


class GoogleSheetsBackend(StorageBackend):
    backend_name = "Google Sheets"

    def __init__(self, connection_name: str = "gsheets"):
        self.connection_name = connection_name

    def _get_connection(self):
        from streamlit_gsheets import GSheetsConnection
        return st.connection(self.connection_name, type=GSheetsConnection)

    def save_checkin(
        self,
        name: str,
        mood: str,
        note: str,
        photo_path: Optional[str] = None,
        **kwargs,
    ) -> bool:
        import pandas as pd
        try:
            conn = self._get_connection()
            try:
                df = conn.read(ttl=0)
                if df is None or not isinstance(df, pd.DataFrame):
                    df = pd.DataFrame(columns=["created_at", "name", "mood", "note", "photo_path"])
            except Exception:
                df = pd.DataFrame(columns=["created_at", "name", "mood", "note", "photo_path"])

            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([
                {
                    "created_at": now_iso,
                    "name": name.strip(),
                    "mood": mood,
                    "note": note.strip() if note else "",
                    "photo_path": photo_path or "",
                }
            ])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(data=updated_df)
            return True
        except Exception as e:
            st.error(f"Error saving to Google Sheets: {e}")
            return False

    def get_recent_checkins(self, limit: int = 50) -> List[Dict[str, Any]]:
        import pandas as pd
        try:
            conn = self._get_connection()
            df = conn.read(ttl=0)
            if df is None or df.empty:
                return []
            
            # Ensure expected columns exist
            for col in ["created_at", "name", "mood", "note", "photo_path"]:
                if col not in df.columns:
                    df[col] = ""

            df = df.fillna("")
            records = df.to_dict(orient="records")
            # Return last N records in reverse order
            return list(reversed(records[-limit:]))
        except Exception as e:
            st.error(f"Error reading from Google Sheets: {e}")
            return []


def get_storage() -> StorageBackend:
    """
    Factory function to initialize the appropriate storage backend.
    Checks st.secrets for Supabase or Google Sheets configurations,
    falling back gracefully to local SQLite.
    """
    # 1. Check Supabase
    try:
        if "supabase" in st.secrets:
            supabase_conf = st.secrets["supabase"]
            if isinstance(supabase_conf, dict):
                url = supabase_conf.get("url")
                key = supabase_conf.get("key")
                if url and key and not str(url).startswith("https://your-project-id"):
                    return SupabaseBackend(url=url, key=key)
    except (FileNotFoundError, KeyError):
        pass
    except Exception as e:
        if "No secrets found" not in str(e):
            print(f"Supabase init check notice: {e}")

    # 2. Check Google Sheets
    try:
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            return GoogleSheetsBackend()
    except (FileNotFoundError, KeyError):
        pass
    except Exception as e:
        if "No secrets found" not in str(e):
            print(f"Google Sheets init check notice: {e}")

    # 3. Fallback to Local SQLite
    return SQLiteBackend()
