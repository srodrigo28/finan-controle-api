"""Health check exigido pelo nginx da VPS (fora do prefixo /api/v1)."""
from flask import Blueprint, jsonify
from sqlalchemy import text

from app.extensoes import db

bp = Blueprint("saude", __name__)


@bp.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
        banco = "ok"
        status = 200
    except Exception as e:  # noqa: BLE001
        banco = f"erro: {e.__class__.__name__}"
        status = 503
    return jsonify({"status": "ok" if status == 200 else "degradado", "banco": banco}), status
