"""Configuração da aplicação lida de variáveis de ambiente."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _lista(valor: str | None) -> list[str]:
    return [v.strip() for v in (valor or "").split(",") if v.strip()]


def _bool(valor: str | None, padrao: bool) -> bool:
    if valor is None or valor.strip() == "":
        return padrao
    return valor.strip().lower() in {"1", "true", "yes", "on"}


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

    # Bucket (99dev.pro/bucket) — sem BUCKET_URL os anexos ficam em disco (dev)
    BUCKET_URL = os.getenv("BUCKET_URL", "").rstrip("/")
    BUCKET_DEFAULT = os.getenv("BUCKET_DEFAULT", "")
    BUCKET_TOKEN = os.getenv("BUCKET_TOKEN", "")
    BUCKET_TIMEOUT = int(os.getenv("BUCKET_TIMEOUT", "20"))

    # Web Push (VAPID) e token do cron de lembretes
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
    VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:contato@99dev.pro")
    CRON_TOKEN = os.getenv("CRON_TOKEN", "")
    APP_URL = os.getenv("APP_URL", "https://finan-controle.vercel.app")

    # E-mail (SMTP) — padrão 99dev, mesmas chaves do SUWAVE para o bloco de .env
    # ser copiável entre projetos. MAIL_HOST vazio = a API só loga (dev sem SMTP).
    MAIL_FROM = os.getenv("MAIL_FROM", "Finan Controle <no-reply@99dev.pro>")
    MAIL_HOST = os.getenv("MAIL_HOST", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_USE_TLS = _bool(os.getenv("MAIL_USE_TLS"), True)
    # Envio em thread: o SMTP tem timeout de 20 s e o cadastro não pode ficar
    # pendurado nele. Desligado nos testes (nada a esperar) e útil desligar em
    # dev quando se quer ver a exceção do envio na hora.
    MAIL_ASYNC = _bool(os.getenv("MAIL_ASYNC"), True)

    # Confirmação de cadastro (código de 4 dígitos)
    EMAIL_VERIFICATION_TOKEN_EXPIRES_HOURS = int(os.getenv("EMAIL_VERIFICATION_TOKEN_EXPIRES_HOURS", "24"))
    EMAIL_VERIFICATION_RESEND_SECONDS = int(os.getenv("EMAIL_VERIFICATION_RESEND_SECONDS", "60"))
    EMAIL_VERIFICATION_MAX_ATTEMPTS = int(os.getenv("EMAIL_VERIFICATION_MAX_ATTEMPTS", "5"))
    # Código MESTRE: 4 dígitos que confirmam QUALQUER conta sem e-mail nenhum.
    # Vazio = desligado (produção). Cada uso vira aviso no log.
    EMAIL_VERIFICATION_TEST_CODE = os.getenv("EMAIL_VERIFICATION_TEST_CODE", "").strip()

    # Esqueci minha senha (link com token opaco)
    PASSWORD_RESET_TOKEN_EXPIRES_HOURS = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRES_HOURS", "2"))
    PASSWORD_RESET_RESEND_SECONDS = int(os.getenv("PASSWORD_RESET_RESEND_SECONDS", "60"))


class ConfigTeste(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL_TESTE",
        "postgresql+psycopg://finan_user:x@127.0.0.1:5436/finan_controle",
    )
    UPLOAD_DIR = str(RAIZ / "uploads_teste")
    BUCKET_URL = ""  # testes: disco (o cliente do bucket é testado com mock)
    VAPID_PUBLIC_KEY = "BF3TPGxPXsNOdeHoRfscTESTE"
    VAPID_PRIVATE_KEY = ""
    CRON_TOKEN = "cron-teste"
    MAIL_HOST = ""  # nenhum teste toca a rede: o serviço de e-mail só loga
    MAIL_ASYNC = False
    # Ligado, o código mestre faria o teste do caminho errado passar. Quem testa
    # o atalho liga por `monkeypatch` dentro do próprio teste.
    EMAIL_VERIFICATION_TEST_CODE = ""
