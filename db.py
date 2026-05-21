"""
db.py  —  Database layer for the session monitor.
Reads all connection details from credentials.py.
Uses pyodbc for ODBC connections (SQL Server, etc.)
"""

from __future__ import annotations
import pyodbc
from datetime import datetime, date, time as time_type
from typing import Optional

import credentials as cfg


# ─── Build ODBC connection string ───────────────────────────────────────────

def _build_connection_string() -> str:
    """Build ODBC connection string from credentials."""
    if cfg.ODBC_TRUSTED_CONNECTION:
        return (
            f"Driver={{{cfg.ODBC_DRIVER}}};"
            f"Server={cfg.ODBC_SERVER};"
            f"Database={cfg.ODBC_DATABASE};"
            f"Trusted_Connection=yes;"
        )
    else:
        return (
            f"Driver={{{cfg.ODBC_DRIVER}}};"
            f"Server={cfg.ODBC_SERVER};"
            f"Database={cfg.ODBC_DATABASE};"
            f"UID={cfg.ODBC_USER};"
            f"PWD={cfg.ODBC_PASSWORD};"
        )


def get_connection():
    """Create and return a new ODBC connection."""
    return pyodbc.connect(_build_connection_string())


# ─── One-time setup ──────────────────────────────────────────────────────────

def init_db() -> None:
    """Create the sessions table if it does not exist yet."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'sessions')
            CREATE TABLE sessions (
                id INT PRIMARY KEY IDENTITY(1,1),
                date DATE NOT NULL,
                time TIME NOT NULL,
                foldername NVARCHAR(255) NOT NULL UNIQUE,
                site NVARCHAR(255) NOT NULL DEFAULT '',
                isUpload BIT NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ─── CRUD operations ─────────────────────────────────────────────────────────

def folder_exists(foldername: str) -> bool:
    """Return True if this foldername is already in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM sessions WHERE foldername = ?",
            (foldername,)
        )
        result = cursor.fetchone()
        return result is not None
    finally:
        cursor.close()
        conn.close()


def add_session(
    foldername: str,
    site: str = "",
    detected_at: Optional[datetime] = None,
) -> dict:
    """Insert a new row. Returns the created session as a dict."""
    now = detected_at or datetime.now()
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            INSERT INTO sessions (date, time, foldername, site, isUpload)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                now.date(),
                now.time().replace(microsecond=0),
                foldername,
                site or cfg.DEFAULT_SITE,
            )
        )
        conn.commit()
        
        # Get the inserted row
        cursor.execute(
            "SELECT id, date, time, foldername, site, isUpload FROM sessions WHERE foldername = ?",
            (foldername,)
        )
        row = cursor.fetchone()
        
        return {
            "id": row[0],
            "date": str(row[1]),
            "time": str(row[2]),
            "foldername": row[3],
            "site": row[4],
            "isUpload": bool(row[5]),
        }
    finally:
        cursor.close()
        conn.close()


def get_all_sessions() -> list[dict]:
    """Return all rows as a list of dicts, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT id, date, time, foldername, site, isUpload FROM sessions ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "date": str(row[1]),
                "time": str(row[2]),
                "foldername": row[3],
                "site": row[4],
                "isUpload": bool(row[5]),
            }
            for row in rows
        ]
    finally:
        cursor.close()
        conn.close()


def get_session(session_id: int) -> Optional[dict]:
    """Return one row as a dict, or None if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT id, date, time, foldername, site, isUpload FROM sessions WHERE id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row[0],
                "date": str(row[1]),
                "time": str(row[2]),
                "foldername": row[3],
                "site": row[4],
                "isUpload": bool(row[5]),
            }
        return None
    finally:
        cursor.close()
        conn.close()


def update_session(session_id: int, **fields) -> Optional[dict]:
    """
    Update any combination of: date, time, foldername, site, isUpload.
    Returns updated dict, or None if id not found.
    """
    allowed = {"date", "time", "foldername", "site", "isUpload"}
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Check if row exists
        cursor.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            return None
        
        # Build dynamic UPDATE statement
        updates = []
        values = []
        for key, val in fields.items():
            if key in allowed:
                updates.append(f"{key} = ?")
                values.append(val)
        
        if not updates:
            # No valid fields to update, return current state
            return get_session(session_id)
        
        values.append(session_id)
        query = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, values)
        conn.commit()
        
        return get_session(session_id)
    finally:
        cursor.close()
        conn.close()


def delete_session(session_id: int) -> bool:
    """Delete a row by id. Returns True if deleted, False if not found."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        conn.close()


def mark_uploaded(session_id: int) -> Optional[dict]:
    """Shortcut: set isUpload = True for the given id."""
    return update_session(session_id, isUpload=True)
