"""Configuração da aplicação lida de variáveis de ambiente."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _lista(valor: str | None) -> list[str]:
    return [v.strip() for v in (valor or "").split(",") if v.strip()]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_ACCESS_HORAS", "12")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DIAS", "30")))
    JWT_TOKEN_LOCATION = ["headers"]

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://finan_user:finan_dev_senha@127.0.0.1:5434/finan_controle",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = _lista(os.getenv("CORS_ORIGINS", "http://localhost:3000"))
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(RAIZ / "uploads"))
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB por anexo
    FUSO_HORARIO = "America/Sao_Paulo"
    JSON_SORT_KEYS = False


class ConfigTeste(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL_TESTE",
        "postgresql+psycopg://finan_user:x@127.0.0.1:5436/finan_controle",
    )
    UPLOAD_DIR = str(RAIZ / "uploads_teste")
