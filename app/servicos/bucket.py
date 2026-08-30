"""Cliente do Bucket (99dev.pro/bucket) — molde do SUWAVE (`bucket_service.py`).

Sem `BUCKET_URL` configurado, a API guarda anexos em disco (modo dev). O token nunca aparece em log nem em resposta.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests
from flask import current_app
from werkzeug.datastructures import FileStorage

from app.erros import ErroApi

log = logging.getLogger(__name__)
INDISPONIVEL = "O serviço de arquivos está indisponível agora. Tente anexar de novo em alguns minutos."


@dataclass
class ArquivoNoBucket:
    file_id: int
    url: str
    tamanho: int
    tipo_mime: str


def configurado() -> bool:
    cfg = current_app.config
    return bool(cfg.get("BUCKET_URL") and cfg.get("BUCKET_DEFAULT") and cfg.get("BUCKET_TOKEN"))


def _cabecalhos() -> dict:
    return {"X-API-Token": current_app.config["BUCKET_TOKEN"]}


def enviar(arquivo: FileStorage, pasta: str, nome: str | None = None) -> ArquivoNoBucket:
    cfg = current_app.config
    nome_arquivo = Path(nome or arquivo.filename or "arquivo").name
    arquivo.stream.seek(0)
    try:
        r = requests.post(
            f"{cfg['BUCKET_URL']}/api/upload",
            headers=_cabecalhos(),
            data={"bucket": cfg["BUCKET_DEFAULT"], "pasta_virtual": pasta},
            files={"arquivo": (nome_arquivo, arquivo.stream, arquivo.mimetype or "application/octet-stream")},
            timeout=cfg.get("BUCKET_TIMEOUT", 20),
        )
    except requests.RequestException as exc:
        log.error("bucket inalcançável: pasta=%s erro=%s", pasta, exc)
        raise ErroApi("ARQUIVOS_INDISPONIVEL", INDISPONIVEL, 503) from exc

    if r.status_code >= 500:
        log.error("bucket 5xx: status=%s pasta=%s corpo=%s", r.status_code, pasta, r.text[:300])
        raise ErroApi("ARQUIVOS_INDISPONIVEL", INDISPONIVEL, 503)
    if r.status_code >= 400:
        log.error("bucket recusou: status=%s pasta=%s corpo=%s", r.status_code, pasta, r.text[:300])
        try:
            msg = r.json().get("message") or "O serviço de arquivos recusou o envio."
        except ValueError:
            msg = "O serviço de arquivos recusou o envio."
        raise ErroApi("ARQUIVO_RECUSADO", msg, 502)

    try:
        corpo = r.json()
    except ValueError as exc:
        raise ErroApi("ARQUIVOS_INDISPONIVEL", INDISPONIVEL, 502) from exc
    if not corpo.get("ok") or not corpo.get("url"):
        raise ErroApi("ARQUIVOS_INDISPONIVEL", INDISPONIVEL, 502)
    return ArquivoNoBucket(
        file_id=int(corpo["file_id"]),
        url=corpo["url"],
        tamanho=int(corpo.get("size_bytes") or 0),
        tipo_mime=corpo.get("mime_type") or arquivo.mimetype or "application/octet-stream",
    )


def apagar(file_id: int) -> bool:
    """Best-effort: falha do bucket não impede a exclusão do anexo no Finan."""
    cfg = current_app.config
    try:
        r = requests.delete(f"{cfg['BUCKET_URL']}/api/files/{file_id}", headers=_cabecalhos(), timeout=cfg.get("BUCKET_TIMEOUT", 20))
        if r.status_code >= 400:
            log.warning("bucket não apagou file_id=%s status=%s", file_id, r.status_code)
            return False
        return True
    except requests.RequestException as exc:
        log.warning("bucket inalcançável ao apagar file_id=%s: %s", file_id, exc)
        return False


def baixar(url: str) -> tuple[bytes, str]:
    """Baixa o conteúdo pela URL do bucket (a API é a porta de entrada; o front nunca vê a URL)."""
    cfg = current_app.config
    try:
        r = requests.get(url, headers=_cabecalhos(), timeout=cfg.get("BUCKET_TIMEOUT", 20))
    except requests.RequestException as exc:
        raise ErroApi("ARQUIVOS_INDISPONIVEL", INDISPONIVEL, 503) from exc
    if r.status_code == 404:
        raise ErroApi("NAO_ENCONTRADO", "Arquivo não encontrado no serviço de arquivos.", 404)
    if r.status_code >= 400:
        raise ErroApi("ARQUIVOS_INDISPONIVEL", INDISPONIVEL, 503)
    return r.content, r.headers.get("Content-Type", "application/octet-stream")
