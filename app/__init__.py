"""Fábrica da aplicação Flask."""
import logging
import os

from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.erros import registrar_handlers
from app.extensoes import cors, db, jwt, migrate

PREFIXO_API = "/api/v1"


class _ScriptName:
    """Aplica X-Script-Name como SCRIPT_NAME (a VPS publica a API em /finan-controle-api/)."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        prefixo = environ.get("HTTP_X_SCRIPT_NAME")
        if prefixo and not environ.get("SCRIPT_NAME"):
            environ["SCRIPT_NAME"] = prefixo.rstrip("/")
            caminho = environ.get("PATH_INFO", "")
            if caminho.startswith(prefixo):
                environ["PATH_INFO"] = caminho[len(prefixo):] or "/"
        return self.app(environ, start_response)


def create_app(config: type[Config] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config or Config)
    app.json.sort_keys = False

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app.wsgi_app = _ScriptName(ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1))

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(
        app,
        resources={r"/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=False,
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Disposition"],
    )

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    from app import modelos  # noqa: F401  (registra os modelos no metadata)
    from app.rotas import auth, categorias, contas, docs, exportar, lancamentos, metricas, notificacoes, precos, saude, sessoes

    app.register_blueprint(saude.bp)
    app.register_blueprint(docs.bp)
    for modulo in (auth, categorias, lancamentos, sessoes, precos, contas, metricas, exportar, notificacoes):
        app.register_blueprint(modulo.bp, url_prefix=PREFIXO_API + modulo.bp.url_prefix)

    registrar_handlers(app)
    _handlers_jwt()
    return app


def _handlers_jwt() -> None:
    def _erro(codigo: str, mensagem: str, status: int):
        return jsonify({"erro": {"codigo": codigo, "mensagem": mensagem, "detalhes": {}}}), status

    @jwt.unauthorized_loader
    def _sem_token(motivo):
        return _erro("NAO_AUTENTICADO", "Token de acesso ausente.", 401)

    @jwt.invalid_token_loader
    def _token_invalido(motivo):
        return _erro("NAO_AUTENTICADO", "Token inválido.", 401)

    @jwt.expired_token_loader
    def _token_expirado(cabecalho, dados):
        return _erro("TOKEN_EXPIRADO", "Token expirado.", 401)

    @jwt.revoked_token_loader
    def _token_revogado(cabecalho, dados):
        return _erro("NAO_AUTENTICADO", "Token revogado.", 401)
