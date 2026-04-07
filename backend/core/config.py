import os
from pathlib import Path


BACKEND_DIR = Path(__file__).parent.parent.absolute()
DATA_DIR    = BACKEND_DIR / "data"
CHROMA_DIR  = str(DATA_DIR / "chroma")
SQLITE_PATH = str(DATA_DIR / "TraceMind.db")

DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL  = os.getenv("DATABASE_URL", f"sqlite:///{SQLITE_PATH}")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
SECRET_KEY    = os.getenv("SECRET_KEY", "change_in_production")
ENVIRONMENT   = os.getenv("ENVIRONMENT", "development")