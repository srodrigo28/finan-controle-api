"""PDF protegido por senha (extrato e fatura costumam vir com parte do CPF).

A senha só abre uma CÓPIA em memória para a leitura pela IA: nunca é gravada, nem logada, e o
original guardado continua protegido.
"""
from __future__ import annotations

import io
import logging

from pypdf import PdfReader, PdfWriter
from pypdf import PasswordType
from pypdf.errors import PyPdfError

log = logging.getLogger(__name__)


def _leitor(conteudo: bytes) -> PdfReader | None:
    try:
        return PdfReader(io.BytesIO(conteudo))
    except (PyPdfError, ValueError, OSError):
        return None  # PDF malformado: a leitura pela IA decide (e vira `erro` legível se falhar)


def esta_protegido(conteudo: bytes) -> bool:
    leitor = _leitor(conteudo)
    return bool(leitor and leitor.is_encrypted)


def abrir(conteudo: bytes, senha: str) -> bytes | None:
    """Cópia do PDF sem senha, ou None se a senha não abre. PDF sem proteção volta igual."""
    leitor = _leitor(conteudo)
    if leitor is None or not leitor.is_encrypted:
        return conteudo
    try:
        if leitor.decrypt(senha) == PasswordType.NOT_DECRYPTED:
            return None
        escritor = PdfWriter(clone_from=leitor)
        saida = io.BytesIO()
        escritor.write(saida)
        return saida.getvalue()
    except (PyPdfError, ValueError, NotImplementedError) as e:
        # Sem a senha no log: só o tipo do erro.
        log.warning("pdf: não foi possível abrir o PDF protegido (%s)", type(e).__name__)
        return None
