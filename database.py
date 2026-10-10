import sqlite3
import json
import uuid
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from backend.config import settings


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.sqlite_db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for high performance concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _ensure_column(cursor: sqlite3.Cursor, table: str, column: str, col_type: str):
    try:
        cursor.execute(f"PRAGMA table_info({table});")
        cols = [r[1] for r in cursor.fetchall()]
        if cols and column not in cols:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type};")
    except Exception as e:
        print(f"Column check notice ({table}.{column}): {e}")


def init_db():
    conn = sqlite3.connect(settings.sqlite_db_path, timeout=30.0)
    conn.isolation_level = None  # Autocommit mode for DDL schema initialization
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=OFF;")
        cursor.execute("PRAGMA busy_timeout=30000;")

        # Demo User Accounts Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS demo_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT DEFAULT 'commuter',
            created_at TEXT
        );
        """)

        # Simulated Wallet Accounts Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_accounts (
            user_id TEXT PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 5000.0,
            currency TEXT NOT NULL DEFAULT 'INR',
            is_simulated INTEGER DEFAULT 1,
            updated_at TEXT,
            FOREIGN KEY (user_id) REFERENCES demo_users(username)
        );
        """)

        # Wallet Transactions Ledger (Audit Trail)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            txn_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            txn_type TEXT NOT NULL, -- CREDIT, DEBIT, REFUND
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'INR',
            balance_after REAL NOT NULL,
            booking_id TEXT,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'SUCCESS', -- SUCCESS, FAILED, REVERSED
            idempotency_key TEXT UNIQUE,
            is_simulated INTEGER DEFAULT 1,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES demo_users(username)
        );
        """)

        # User Preferences
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            max_budget REAL DEFAULT 2000.0,
            latest_arrival_time TEXT DEFAULT '09:00',
            preferred_modes TEXT DEFAULT '["metro", "express_train", "bus", "rideshare"]',
            seat_preference TEXT DEFAULT 'window',
            payment_mode_preference TEXT DEFAULT 'ONLINE_WALLET', -- ONLINE_WALLET, OFFLINE_PAY_LATER
            auto_book_enabled INTEGER DEFAULT 0,
            auto_book_authorized INTEGER DEFAULT 0,
            ranking_strategy TEXT DEFAULT 'balanced',
            max_walking_minutes INTEGER DEFAULT 15,
            notification_channel TEXT DEFAULT 'ui',
            updated_at TEXT
        );
        """)

        # Migrate user_preferences columns if existing table had older schema
        _ensure_column(cursor, "user_preferences", "max_budget", "REAL DEFAULT 2000.0")
        _ensure_column(cursor, "user_preferences", "latest_arrival_time", "TEXT DEFAULT '09:00'")
        _ensure_column(cursor, "user_preferences", "preferred_modes", "TEXT DEFAULT '[\"metro\", \"express_train\", \"bus\", \"rideshare\"]'")
        _ensure_column(cursor, "user_preferences", "seat_preference", "TEXT DEFAULT 'window'")
        _ensure_column(cursor, "user_preferences", "payment_mode_preference", "TEXT DEFAULT 'ONLINE_WALLET'")
        _ensure_column(cursor, "user_preferences", "auto_book_enabled", "INTEGER DEFAULT 0")
        _ensure_column(cursor, "user_preferences", "auto_book_authorized", "INTEGER DEFAULT 0")
        _ensure_column(cursor, "user_preferences", "ranking_strategy", "TEXT DEFAULT 'balanced'")
        _ensure_column(cursor, "user_preferences", "max_walking_minutes", "INTEGER DEFAULT 15")
        _ensure_column(cursor, "user_preferences", "notification_channel", "TEXT DEFAULT 'ui'")
        _ensure_column(cursor, "user_preferences", "updated_at", "TEXT")

        # Agent Sessions & Task States
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT DEFAULT 'demo_commuter',
            status TEXT,
            request_json TEXT,
            plan_response_json TEXT,
            recommended_option_id TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """)
        _ensure_column(cursor, "agent_sessions", "user_id", "TEXT DEFAULT 'demo_commuter'")
        _ensure_column(cursor, "agent_sessions", "status", "TEXT")
        _ensure_column(cursor, "agent_sessions", "request_json", "TEXT")
        _ensure_column(cursor, "agent_sessions", "plan_response_json", "TEXT")
        _ensure_column(cursor, "agent_sessions", "recommended_option_id", "TEXT")
        _ensure_column(cursor, "agent_sessions", "created_at", "TEXT")
        _ensure_column(cursor, "agent_sessions", "updated_at", "TEXT")

        # Tool Execution Logs
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            tool_name TEXT,
            input_params TEXT,
            output_result TEXT,
            execution_time_ms REAL,
            status TEXT,
            error_message TEXT,
            timestamp TEXT
        );
        """)
        _ensure_column(cursor, "tool_logs", "session_id", "TEXT")
        _ensure_column(cursor, "tool_logs", "tool_name", "TEXT")
        _ensure_column(cursor, "tool_logs", "input_params", "TEXT")
        _ensure_column(cursor, "tool_logs", "output_result", "TEXT")
        _ensure_column(cursor, "tool_logs", "execution_time_ms", "REAL")
        _ensure_column(cursor, "tool_logs", "status", "TEXT")
        _ensure_column(cursor, "tool_logs", "error_message", "TEXT")
        _ensure_column(cursor, "tool_logs", "timestamp", "TEXT")

        # Bookings table with idempotency, verification, payment mode & receipt
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id TEXT PRIMARY KEY,
            session_id TEXT,
            option_id TEXT,
            provider_id TEXT,
            origin TEXT,
            destination TEXT,
            journey_date TEXT,
            departure_time TEXT,
            arrival_time TEXT,
            passenger_name TEXT,
            passenger_count INTEGER,
            seat_number TEXT,
            seat_type TEXT,
            total_amount REAL,
            currency TEXT DEFAULT 'INR',
            payment_mode TEXT DEFAULT 'ONLINE_WALLET', -- ONLINE_WALLET, OFFLINE_PAY_LATER
            payment_status TEXT DEFAULT 'PAID',       -- PAID, PENDING_PAYMENT, REFUNDED, FAILED
            status TEXT,                              -- CONFIRMED, FAILED, PENDING, CANCELLED
            is_auto_booked INTEGER,
            is_mock INTEGER DEFAULT 1,
            verification_code TEXT,
            idempotency_key TEXT UNIQUE,
            failure_reason TEXT,
            receipt_json TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        """)

        # Column migrations for existing tables
        _ensure_column(cursor, "bookings", "payment_mode", "TEXT DEFAULT 'ONLINE_WALLET'")
        _ensure_column(cursor, "bookings", "payment_status", "TEXT DEFAULT 'PAID'")
        _ensure_column(cursor, "bookings", "currency", "TEXT DEFAULT 'INR'")
        _ensure_column(cursor, "bookings", "seat_type", "TEXT")
        _ensure_column(cursor, "bookings", "is_mock", "INTEGER DEFAULT 1")
        _ensure_column(cursor, "bookings", "verification_code", "TEXT")
        _ensure_column(cursor, "bookings", "idempotency_key", "TEXT UNIQUE")
        _ensure_column(cursor, "bookings", "failure_reason", "TEXT")
        _ensure_column(cursor, "bookings", "receipt_json", "TEXT")
        _ensure_column(cursor, "wallet_accounts", "currency", "TEXT DEFAULT 'INR'")
        _ensure_column(cursor, "wallet_accounts", "is_simulated", "INTEGER DEFAULT 1")
        _ensure_column(cursor, "wallet_transactions", "currency", "TEXT DEFAULT 'INR'")
        _ensure_column(cursor, "wallet_transactions", "is_simulated", "INTEGER DEFAULT 1")
        _ensure_column(cursor, "wallet_transactions", "idempotency_key", "TEXT UNIQUE")

        # Commute History
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS commute_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            origin TEXT,
            destination TEXT,
            chosen_mode TEXT,
            fare REAL,
            duration_minutes INTEGER,
            arrival_status TEXT,
            timestamp TEXT
        );
        """)

        # Live Commute Tracking Telemetry
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS live_trips (
            trip_id TEXT PRIMARY KEY,
            booking_id TEXT,
            origin TEXT,
            destination TEXT,
            current_lat REAL,
            current_lon REAL,
            current_stop TEXT,
            next_stop TEXT,
            progress_percentage REAL,
            speed_kmh REAL,
            eta_minutes INTEGER,
            status TEXT, -- SCHEDULED, IN_TRANSIT, DELAYED, COMPLETED
            updated_at TEXT
        );
        """)

        # Seed Default Demo User & Initial ₹5,000 Wallet
        demo_user = settings.demo_default_username
        now_str = datetime.now().isoformat()
        
        cursor.execute("""
        INSERT OR IGNORE INTO demo_users (username, password_hash, display_name, email, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            demo_user,
            hash_password(settings.demo_default_password),
            "Demo Commuter",
            "demo.commuter@example.com",
            now_str
        ))

        try:
            cursor.execute("""
            INSERT OR IGNORE INTO users (username, password_hash, display_name, email, created_at)
            VALUES (?, ?, ?, ?, ?)
            """, (
                demo_user,
                hash_password(settings.demo_default_password),
                "Demo Commuter",
                "demo.commuter@example.com",
                now_str
            ))
        except Exception:
            pass

        cursor.execute("SELECT user_id FROM wallet_accounts WHERE user_id = ?", (demo_user,))
        if not cursor.fetchone():
            # Initial ₹5,000 demo wallet
            cursor.execute("""
            INSERT INTO wallet_accounts (user_id, balance, currency, is_simulated, updated_at)
            VALUES (?, ?, ?, 1, ?)
            """, (demo_user, settings.initial_wallet_balance, settings.default_currency, now_str))

            # Initial seed transaction record
            cursor.execute("""
            INSERT INTO wallet_transactions (
                txn_id, user_id, txn_type, amount, currency, balance_after,
                booking_id, description, status, idempotency_key, is_simulated, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                f"TXN-INIT-{uuid.uuid4().hex[:8].upper()}",
                demo_user,
                "CREDIT",
                settings.initial_wallet_balance,
                settings.default_currency,
                settings.initial_wallet_balance,
                None,
                "Initial Simulated Demo Wallet Grant (₹5,000)",
                "SUCCESS",
                "seed_init_grant_001",
                now_str
            ))

        # Seed default user preferences if not exist
        cursor.execute("SELECT user_id FROM user_preferences WHERE user_id = ?", (demo_user,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO user_preferences (
                user_id, max_budget, latest_arrival_time, preferred_modes, 
                seat_preference, payment_mode_preference, auto_book_enabled, auto_book_authorized, 
                ranking_strategy, max_walking_minutes, notification_channel, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                demo_user, 2000.0, '09:00', json.dumps(["metro", "express_train", "bus", "rideshare"]),
                'window', 'ONLINE_WALLET', 0, 0, 'balanced', 15, 'ui', now_str
            ))

        cursor.execute("PRAGMA foreign_keys=ON;")
    finally:
        conn.close()


# =====================================================================
# AUTH & DEMO ACCOUNT HELPERS
# =====================================================================
def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM demo_users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and row["password_hash"] == hash_password(password):
        return {
            "username": row["username"],
            "display_name": row["display_name"],
            "email": row["email"],
            "role": row["role"],
            "created_at": row["created_at"]
        }
    return None


def get_demo_user(username: str = "demo_commuter") -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM demo_users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "username": row["username"],
            "display_name": row["display_name"],
            "email": row["email"],
            "role": row["role"],
            "created_at": row["created_at"]
        }
    return None


def _ensure_demo_user(cursor: sqlite3.Cursor, user_id: str):
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT OR IGNORE INTO demo_users (username, password_hash, display_name, email, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, hash_password("demo123"), user_id, f"{user_id}@example.com", now_str))


# =====================================================================
# WALLET ATOMIC OPERATIONS & SAFETY
# =====================================================================
def get_wallet(user_id: str = "demo_commuter") -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    _ensure_demo_user(cursor, user_id)
    cursor.execute("SELECT * FROM wallet_accounts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        res = {
            "user_id": row["user_id"],
            "balance": round(float(row["balance"]), 2),
            "currency": row["currency"],
            "is_simulated": bool(row["is_simulated"]),
            "updated_at": row["updated_at"]
        }
        conn.commit()
        conn.close()
        return res

    # Create if missing
    now_str = datetime.now().isoformat()
    cursor.execute("INSERT OR IGNORE INTO wallet_accounts (user_id, balance, currency, is_simulated, updated_at) VALUES (?, ?, ?, 1, ?)",
                   (user_id, settings.initial_wallet_balance, settings.default_currency, now_str))
    conn.commit()
    conn.close()
    return {
        "user_id": user_id,
        "balance": settings.initial_wallet_balance,
        "currency": settings.default_currency,
        "is_simulated": True,
        "updated_at": now_str
    }


def topup_wallet(user_id: str, amount: float, description: str = "Simulated Wallet Top-up") -> Dict[str, Any]:
    if amount <= 0:
        raise ValueError("Top-up amount must be strictly greater than 0.")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        _ensure_demo_user(cursor, user_id)
        
        cursor.execute("SELECT balance, currency FROM wallet_accounts WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            current_balance = 0.0
            currency = settings.default_currency
        else:
            current_balance = float(row["balance"])
            currency = row["currency"]

        new_balance = round(current_balance + amount, 2)
        now_str = datetime.now().isoformat()
        txn_id = f"TXN-TOP-{uuid.uuid4().hex[:8].upper()}"

        cursor.execute("""
        INSERT INTO wallet_accounts (user_id, balance, currency, is_simulated, updated_at)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(user_id) DO UPDATE SET balance = excluded.balance, updated_at = excluded.updated_at
        """, (user_id, new_balance, currency, now_str))

        cursor.execute("""
        INSERT INTO wallet_transactions (
            txn_id, user_id, txn_type, amount, currency, balance_after,
            booking_id, description, status, idempotency_key, is_simulated, timestamp
        ) VALUES (?, ?, 'CREDIT', ?, ?, ?, NULL, ?, 'SUCCESS', ?, 1, ?)
        """, (txn_id, user_id, amount, currency, new_balance, description, f"topup_{txn_id}", now_str))

        conn.commit()
        return {
            "success": True,
            "txn_id": txn_id,
            "user_id": user_id,
            "amount_added": amount,
            "new_balance": new_balance,
            "currency": currency,
            "is_simulated": True,
            "timestamp": now_str
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def process_wallet_payment(
    user_id: str,
    amount: float,
    booking_id: str,
    description: str,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Atomic wallet deduction.
    - If idempotency_key exists and already paid, returns existing transaction without double deduction.
    - If insufficient balance, rejects payment with zero balance deduction.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        _ensure_demo_user(cursor, user_id)

        # Idempotency Check
        if idempotency_key:
            cursor.execute("SELECT * FROM wallet_transactions WHERE idempotency_key = ?", (idempotency_key,))
            existing = cursor.fetchone()
            if existing:
                conn.commit()
                return {
                    "success": existing["status"] == "SUCCESS",
                    "txn_id": existing["txn_id"],
                    "amount_deducted": existing["amount"],
                    "balance_after": existing["balance_after"],
                    "currency": existing["currency"],
                    "booking_id": existing["booking_id"],
                    "status": existing["status"],
                    "is_duplicate_prevented": True
                }

        cursor.execute("SELECT balance, currency FROM wallet_accounts WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        current_balance = float(row["balance"]) if row else 0.0
        currency = row["currency"] if row else settings.default_currency

        if current_balance < amount:
            # Insufficient balance -> REJECT with ZERO deduction
            txn_id = f"TXN-REJ-{uuid.uuid4().hex[:8].upper()}"
            now_str = datetime.now().isoformat()
            cursor.execute("""
            INSERT INTO wallet_transactions (
                txn_id, user_id, txn_type, amount, currency, balance_after,
                booking_id, description, status, idempotency_key, is_simulated, timestamp
            ) VALUES (?, ?, 'DEBIT', ?, ?, ?, ?, ?, 'FAILED', ?, 1, ?)
            """, (txn_id, user_id, amount, currency, current_balance, booking_id, f"FAILED: Insufficient balance ({description})", idempotency_key, now_str))
            
            conn.commit()
            return {
                "success": False,
                "error": f"Insufficient wallet balance. Required: ₹{amount:.2f}, Available: ₹{current_balance:.2f}.",
                "txn_id": txn_id,
                "current_balance": current_balance,
                "amount_attempted": amount,
                "currency": currency,
                "is_simulated": True
            }

        # Sufficient balance -> Deduct exactly once
        new_balance = round(current_balance - amount, 2)
        now_str = datetime.now().isoformat()
        txn_id = f"TXN-DEB-{uuid.uuid4().hex[:8].upper()}"

        cursor.execute("UPDATE wallet_accounts SET balance = ?, updated_at = ? WHERE user_id = ?",
                       (new_balance, now_str, user_id))

        cursor.execute("""
        INSERT INTO wallet_transactions (
            txn_id, user_id, txn_type, amount, currency, balance_after,
            booking_id, description, status, idempotency_key, is_simulated, timestamp
        ) VALUES (?, ?, 'DEBIT', ?, ?, ?, ?, ?, 'SUCCESS', ?, 1, ?)
        """, (txn_id, user_id, amount, currency, new_balance, booking_id, description, idempotency_key, now_str))

        conn.commit()
        return {
            "success": True,
            "txn_id": txn_id,
            "amount_deducted": amount,
            "balance_after": new_balance,
            "currency": currency,
            "booking_id": booking_id,
            "status": "SUCCESS",
            "is_simulated": True,
            "timestamp": now_str
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_wallet_transactions(user_id: str = "demo_commuter", limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =====================================================================
# USER PREFERENCES
# =====================================================================
def save_user_preferences(prefs: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = prefs.get("user_id", "demo_commuter")
    _ensure_demo_user(cursor, user_id)
    now_str = datetime.now().isoformat()
    preferred_modes_json = json.dumps(prefs.get("preferred_modes", []))
    cursor.execute("""
    INSERT INTO user_preferences (
        user_id, max_budget, latest_arrival_time, preferred_modes,
        seat_preference, payment_mode_preference, auto_book_enabled, auto_book_authorized,
        ranking_strategy, max_walking_minutes, notification_channel, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        max_budget = excluded.max_budget,
        latest_arrival_time = excluded.latest_arrival_time,
        preferred_modes = excluded.preferred_modes,
        seat_preference = excluded.seat_preference,
        payment_mode_preference = excluded.payment_mode_preference,
        auto_book_enabled = excluded.auto_book_enabled,
        auto_book_authorized = excluded.auto_book_authorized,
        ranking_strategy = excluded.ranking_strategy,
        max_walking_minutes = excluded.max_walking_minutes,
        notification_channel = excluded.notification_channel,
        updated_at = excluded.updated_at
    """, (
        user_id,
        prefs.get("max_budget", 2000.0),
        prefs.get("latest_arrival_time", "09:00"),
        preferred_modes_json,
        prefs.get("seat_preference", "window"),
        prefs.get("payment_mode_preference", "ONLINE_WALLET"),
        1 if prefs.get("auto_book_enabled", False) else 0,
        1 if prefs.get("auto_book_authorized", False) else 0,
        prefs.get("ranking_strategy", "balanced"),
        prefs.get("max_walking_minutes", 15),
        prefs.get("notification_channel", "ui"),
        now_str
    ))
    conn.commit()
    conn.close()


def get_user_preferences(user_id: str = "demo_commuter") -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row["user_id"],
            "max_budget": row["max_budget"],
            "latest_arrival_time": row["latest_arrival_time"],
            "preferred_modes": json.loads(row["preferred_modes"]),
            "seat_preference": row["seat_preference"],
            "payment_mode_preference": row["payment_mode_preference"] if "payment_mode_preference" in row.keys() else "ONLINE_WALLET",
            "auto_book_enabled": bool(row["auto_book_enabled"]),
            "auto_book_authorized": bool(row["auto_book_authorized"]),
            "ranking_strategy": row["ranking_strategy"],
            "max_walking_minutes": row["max_walking_minutes"],
            "notification_channel": row["notification_channel"],
            "updated_at": row["updated_at"]
        }
    return {
        "user_id": user_id,
        "max_budget": 2000.0,
        "latest_arrival_time": "09:00",
        "preferred_modes": ["metro", "express_train", "bus", "rideshare"],
        "seat_preference": "window",
        "payment_mode_preference": "ONLINE_WALLET",
        "auto_book_enabled": False,
        "auto_book_authorized": False,
        "ranking_strategy": "balanced",
        "max_walking_minutes": 15,
        "notification_channel": "ui"
    }


# =====================================================================
# SESSIONS & TOOL LOGS
# =====================================================================
def save_session_state(session_id: str, status: str, request_data: Dict[str, Any], plan_response: Dict[str, Any], option_id: Optional[str] = None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        now_str = datetime.now().isoformat()
        user_id = request_data.get("user_id", "demo_commuter") if isinstance(request_data, dict) else "demo_commuter"
        _ensure_demo_user(cursor, user_id)
        cursor.execute("""
        INSERT INTO agent_sessions (session_id, user_id, status, request_json, plan_response_json, recommended_option_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            user_id = excluded.user_id,
            status = excluded.status,
            request_json = excluded.request_json,
            plan_response_json = excluded.plan_response_json,
            recommended_option_id = excluded.recommended_option_id,
            updated_at = excluded.updated_at
        """, (
            session_id,
            user_id,
            status,
            json.dumps(request_data),
            json.dumps(plan_response),
            option_id,
            now_str,
            now_str
        ))
        conn.commit()
    finally:
        conn.close()


def get_session_state(session_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            return {
                "session_id": row["session_id"],
                "user_id": row["user_id"] if "user_id" in row.keys() else "demo_commuter",
                "status": row["status"],
                "request": json.loads(row["request_json"]) if row["request_json"] else None,
                "plan_response": json.loads(row["plan_response_json"]) if row["plan_response_json"] else None,
                "recommended_option_id": row["recommended_option_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
        return None
    finally:
        conn.close()


def log_tool_call(session_id: str, tool_name: str, input_params: Any, output_result: Any, execution_time_ms: float, status: str = "SUCCESS", error_message: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO tool_logs (session_id, tool_name, input_params, output_result, execution_time_ms, status, error_message, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        tool_name,
        json.dumps(input_params, default=str),
        json.dumps(output_result, default=str),
        execution_time_ms,
        status,
        error_message,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


def get_tool_logs(session_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute("SELECT * FROM tool_logs WHERE session_id = ? ORDER BY id DESC LIMIT ?", (session_id, limit))
    else:
        cursor.execute("SELECT * FROM tool_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    logs = []
    for r in rows:
        try:
            in_p = json.loads(r["input_params"])
        except Exception:
            in_p = r["input_params"]
        try:
            out_r = json.loads(r["output_result"])
        except Exception:
            out_r = r["output_result"]
        logs.append({
            "id": r["id"],
            "session_id": r["session_id"],
            "tool_name": r["tool_name"],
            "input_params": in_p,
            "output_result": out_r,
            "execution_time_ms": r["execution_time_ms"],
            "status": r["status"],
            "error_message": r["error_message"],
            "timestamp": r["timestamp"]
        })
    return logs


# =====================================================================
# BOOKINGS & RECEIPTS
# =====================================================================
def save_booking(booking_data: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    receipt_str = json.dumps(booking_data.get("receipt", {})) if booking_data.get("receipt") else None
    cursor.execute("""
    INSERT INTO bookings (
        booking_id, session_id, option_id, provider_id, origin, destination,
        journey_date, departure_time, arrival_time, passenger_name, passenger_count,
        seat_number, seat_type, total_amount, currency, payment_mode, payment_status,
        status, is_auto_booked, is_mock, verification_code, idempotency_key, failure_reason,
        receipt_json, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(booking_id) DO UPDATE SET
        status = excluded.status,
        payment_status = excluded.payment_status,
        verification_code = excluded.verification_code,
        failure_reason = excluded.failure_reason,
        receipt_json = excluded.receipt_json,
        updated_at = excluded.updated_at
    """, (
        booking_data.get("booking_id"),
        booking_data.get("session_id", ""),
        booking_data.get("option_id"),
        booking_data.get("provider_id", "mock_transit_adapter"),
        booking_data.get("origin"),
        booking_data.get("destination"),
        booking_data.get("journey_date"),
        booking_data.get("departure_time"),
        booking_data.get("arrival_time"),
        booking_data.get("passenger_name"),
        booking_data.get("passenger_count", 1),
        booking_data.get("seat_number"),
        booking_data.get("seat_type"),
        booking_data.get("total_amount"),
        booking_data.get("currency", "INR"),
        booking_data.get("payment_mode", "ONLINE_WALLET"),
        booking_data.get("payment_status", "PAID"),
        booking_data.get("status"),
        1 if booking_data.get("is_auto_booked") else 0,
        1 if booking_data.get("is_mock", True) else 0,
        booking_data.get("verification_code"),
        booking_data.get("idempotency_key"),
        booking_data.get("failure_reason"),
        receipt_str,
        booking_data.get("created_at", now_str),
        now_str
    ))
    conn.commit()
    conn.close()


def get_booking_by_id(booking_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("receipt_json"):
            try:
                d["receipt"] = json.loads(d["receipt_json"])
            except Exception:
                d["receipt"] = None
        return d
    return None


def get_booking_by_idempotency_key(key: str) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bookings WHERE idempotency_key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        if d.get("receipt_json"):
            try:
                d["receipt"] = json.loads(d["receipt_json"])
            except Exception:
                d["receipt"] = None
        return d
    return None


def get_all_bookings(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("receipt_json"):
            try:
                d["receipt"] = json.loads(d["receipt_json"])
            except Exception:
                d["receipt"] = None
        results.append(d)
    return results


# =====================================================================
# LIVE TRACKING TELEMETRY
# =====================================================================
def update_trip_telemetry(trip_data: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    INSERT INTO live_trips (
        trip_id, booking_id, origin, destination, current_lat, current_lon,
        current_stop, next_stop, progress_percentage, speed_kmh, eta_minutes, status, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(trip_id) DO UPDATE SET
        current_lat = excluded.current_lat,
        current_lon = excluded.current_lon,
        current_stop = excluded.current_stop,
        next_stop = excluded.next_stop,
        progress_percentage = excluded.progress_percentage,
        speed_kmh = excluded.speed_kmh,
        eta_minutes = excluded.eta_minutes,
        status = excluded.status,
        updated_at = excluded.updated_at
    """, (
        trip_data.get("trip_id"),
        trip_data.get("booking_id"),
        trip_data.get("origin"),
        trip_data.get("destination"),
        trip_data.get("current_lat", 12.9716),
        trip_data.get("current_lon", 77.5946),
        trip_data.get("current_stop", "Station A"),
        trip_data.get("next_stop", "Station B"),
        trip_data.get("progress_percentage", 0.0),
        trip_data.get("speed_kmh", 55.0),
        trip_data.get("eta_minutes", 20),
        trip_data.get("status", "IN_TRANSIT"),
        now_str
    ))
    conn.commit()
    conn.close()


def get_trip_telemetry(trip_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM live_trips WHERE trip_id = ?", (trip_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
