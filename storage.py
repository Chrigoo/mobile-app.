"""
Storage layer for Daily Check-In application.
Supports Supabase, Google Sheets (st-gsheets-connection), and local SQLite fallback.
"""

from abc import ABC, abstractmethod
import datetime
import os
import sqlite3
from typing import Optional, List, Dict, Any
import streamlit as st


class StorageBackend(ABC):
    backend_name: str = "Base"

    @abstractmethod
    def save_checkin(self, name: str, mood: str, note: str) -> bool:
        """Save a new check-in entry."""
        pass

    @abstractmethod
    def get_recent_checkins(self, limit: int = 10) -> List[Dict[str, Any]]:
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    name TEXT NOT NULL,
                    mood TEXT NOT NULL,
                    note TEXT
                )
                """
            )
            conn.commit()

    def save_checkin(self, name: str, mood: str, note: str) -> bool:
        try:
            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO checkins (created_at, name, mood, note)
                    VALUES (?, ?, ?, ?)
                    """,
                    (now_iso, name.strip(), mood, note.strip() if note else ""),
                )
                conn.commit()
            return True
        except Exception as e:
            st.error(f"Error saving to SQLite: {e}")
            return False

    def get_recent_checkins(self, limit: int = 10) -> List[Dict[str, Any]]:
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
                return [dict(row) for row in rows]
        except Exception as e:
            st.error(f"Error reading from SQLite: {e}")
            return []


class SupabaseBackend(StorageBackend):
    backend_name = "Supabase"

    def __init__(self, url: str, key: str, table_name: str = "checkins"):
        from supabase import create_client, Client
        self.table_name = table_name
        self.client: Client = create_client(url, key)

    def save_checkin(self, name: str, mood: str, note: str) -> bool:
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            payload = {
                "name": name.strip(),
                "mood": mood,
                "note": note.strip() if note else "",
                "created_at": now_iso,
            }
            res = self.client.table(self.table_name).insert(payload).execute()
            return bool(res.data)
        except Exception as e:
            st.error(f"Error saving to Supabase: {e}")
            return False

    def get_recent_checkins(self, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            res = (
                self.client.table(self.table_name)
                .select("id, created_at, name, mood, note")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
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

    def save_checkin(self, name: str, mood: str, note: str) -> bool:
        import pandas as pd
        try:
            conn = self._get_connection()
            try:
                df = conn.read(ttl=0)
                if df is None or not isinstance(df, pd.DataFrame):
                    df = pd.DataFrame(columns=["created_at", "name", "mood", "note"])
            except Exception:
                df = pd.DataFrame(columns=["created_at", "name", "mood", "note"])

            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_row = pd.DataFrame([
                {
                    "created_at": now_iso,
                    "name": name.strip(),
                    "mood": mood,
                    "note": note.strip() if note else "",
                }
            ])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(data=updated_df)
            return True
        except Exception as e:
            st.error(f"Error saving to Google Sheets: {e}")
            return False

    def get_recent_checkins(self, limit: int = 10) -> List[Dict[str, Any]]:
        import pandas as pd
        try:
            conn = self._get_connection()
            df = conn.read(ttl=0)
            if df is None or df.empty:
                return []
            
            # Ensure expected columns exist
            for col in ["created_at", "name", "mood", "note"]:
                if col not in df.columns:
                    df[col] = ""

            df = df.fillna("")
            records = df.to_dict(orient="records")
            # Return last N records in reverse order
            return list(reversed(records[-limit:]))
        except Exception as e:
            st.error(f"Error reading from Google Sheets: {e}")
            return []


@st.cache_resource
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
            url = supabase_conf.get("url")
            key = supabase_conf.get("key")
            if url and key and not url.startswith("https://your-project-id"):
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

