"""Exceção padrão da API e registro dos handlers no formato do contrato."""
from __future__ import annotations

from flask import Flask, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


class ErroApi(Exception):
    def __init__(self, codigo: str, mensagem: str, status: int = 400, detalhes: dict | None = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status = status
        self.detalhes = detalhes or {}

    def resposta(self):
        return jsonify({"erro": {"codigo": self.codigo, "mensagem": self.mensagem, "detalhes": self.detalhes}}), self.status


def nao_encontrado(recurso: str = "Recurso") -> ErroApi:
    return ErroApi("NAO_ENCONTRADO", f"{recurso} não encontrado.", 404)


def registrar_handlers(app: Flask) -> None:
    @app.errorhandler(ErroApi)
    def _erro_api(e: ErroApi):
        return e.resposta()

    @app.errorhandler(ValidationError)
    def _erro_validacao(e: ValidationError):
        detalhes = {".".join(str(p) for p in err["loc"]) or "_": err["msg"] for err in e.errors()}
        return ErroApi("VALIDACAO", "Dados inválidos.", 422, detalhes).resposta()

    @app.errorhandler(HTTPException)
    def _erro_http(e: HTTPException):
        codigos = {400: "REQUISICAO_INVALIDA", 401: "NAO_AUTENTICADO", 403: "PROIBIDO",
                   404: "NAO_ENCONTRADO", 405: "METODO_NAO_PERMITIDO", 413: "ARQUIVO_GRANDE"}
        return ErroApi(codigos.get(e.code, "ERRO_HTTP"), e.description or e.name, e.code or 500).resposta()

    @app.errorhandler(Exception)
    def _erro_interno(e: Exception):
        app.logger.exception("Erro interno não tratado: %s", e)
        return ErroApi("ERRO_INTERNO", "Erro interno do servidor.", 500).resposta()
