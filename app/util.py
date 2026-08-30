"""Funções utilitárias compartilhadas."""
from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, TypeVar

from flask import request
from flask_jwt_extended import get_jwt_identity
from pydantic import BaseModel

from app.erros import ErroApi

T = TypeVar("T", bound=BaseModel)


def agora() -> datetime:
    return datetime.now(timezone.utc)


def normalizar_descricao(texto: str) -> str:
    """lower, sem acento, espaços colapsados."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def dec(valor: Any, casas: int = 2) -> Decimal:
    q = Decimal(1).scaleb(-casas)
    return Decimal(str(valor)).quantize(q, rounding=ROUND_HALF_UP)


def num(valor: Decimal | None) -> float | None:
    return None if valor is None else float(valor)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def data_iso(d: date | None) -> str | None:
    return None if d is None else d.isoformat()


def uid(valor: str | None) -> str | None:
    return None if valor is None else str(valor)


def validar(esquema: type[T], dados: dict | None = None) -> T:
    """Valida o corpo JSON da requisição (ou `dados`) com o esquema pydantic."""
    corpo = dados if dados is not None else (request.get_json(silent=True) or {})
    if not isinstance(corpo, dict):
        raise ErroApi("VALIDACAO", "Corpo deve ser um objeto JSON.", 422)
    return esquema.model_validate(corpo)


def usuario_id() -> uuid.UUID:
    ident = get_jwt_identity()
    try:
        return uuid.UUID(str(ident))
    except (ValueError, TypeError):
        raise ErroApi("NAO_AUTENTICADO", "Token inválido.", 401)


def parse_uuid(valor: str, nome: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(valor))
    except (ValueError, TypeError):
        raise ErroApi("VALIDACAO", f"{nome} inválido.", 422)


def parse_data(valor: str | None, nome: str = "data", padrao: date | None = None) -> date | None:
    if not valor:
        return padrao
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ErroApi("VALIDACAO", f"{nome} deve estar no formato YYYY-MM-DD.", 422)
