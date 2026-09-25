import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    database_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'cybersafe.db'}")
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"): ]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"): ]
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    WTF_CSRF_ENABLED = True
    UPLOAD_FOLDER = Path(os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "app" / "static" / "uploads")))
