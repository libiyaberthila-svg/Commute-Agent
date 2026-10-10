import os
from pathlib import Path
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"
CHROMA_DB_DIR = BASE_DIR / "chroma_db"
SQLITE_DB_PATH = BASE_DIR / "commute_agent.db"

# Ensure directories exist
KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DB_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseModel):
    app_name: str = "Daily Commute & Autonomous Seat Booking Agent"
    version: str = "2.0.0"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    
    # SQLite
    database_url: str = f"sqlite:///{SQLITE_DB_PATH}"
    sqlite_db_path: str = str(SQLITE_DB_PATH)
    
    # LLM & Embeddings (Optional local Ollama or fallback)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")
    use_llm: bool = os.getenv("USE_LLM", "false").lower() in ("true", "1", "yes")
    
    # Chroma & RAG
    chroma_db_dir: str = str(CHROMA_DB_DIR)
    knowledge_base_dir: str = str(KNOWLEDGE_BASE_DIR)
    
    # Booking & Wallet rules
    max_auto_booking_limit: float = 2500.0  # Max budget in INR for automatic seat bookings without manual signoff
    require_explicit_auth: bool = True
    default_currency: str = "INR"
    currency_symbol: str = "₹"
    initial_wallet_balance: float = 5000.0
    demo_default_username: str = "demo_commuter"
    demo_default_password: str = "demo123"


settings = Settings()

