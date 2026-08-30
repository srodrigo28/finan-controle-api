"""Documentação: Swagger UI na raiz (/ e /docs) e especificação em /openapi.json.

Funciona atrás do prefixo da VPS (/finan-controle-api/): a página usa URL relativa
para o spec e o spec declara `servers` a partir do SCRIPT_NAME da requisição.
"""
from flask import Blueprint, Response, jsonify, request

from app.docs_openapi import montar_spec

bp = Blueprint("docs", __name__)

SWAGGER_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Finan API — documentação</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <style>
    body { margin: 0; background: #fafafa; }
    .topbar { display: none; }
    .swagger-ui .info .title { font-size: 28px; }
  </style>
</head>
<body>
  <div id="swagger"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js" crossorigin></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "openapi.json",
      dom_id: "#swagger",
      deepLinking: true,
      persistAuthorization: true,
      displayRequestDuration: true,
      docExpansion: "list",
      tagsSorter: "alpha",
    });
  </script>
</body>
</html>
"""


@bp.get("/")
@bp.get("/docs")
@bp.get("/docs/")
def swagger_ui():
    return Response(SWAGGER_HTML, mimetype="text/html")


@bp.get("/openapi.json")
def openapi_json():
    servidor = request.script_root or "/"
    return jsonify(montar_spec(servidor))
