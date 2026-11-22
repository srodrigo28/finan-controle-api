"""Importação por IA: guardar o original, ler com o Claude, revisar e confirmar.

Ordem que não perde nada: o arquivo vai para o disco ANTES da leitura (se a IA falhar, dá para reler),
a IA só preenche um rascunho, e só `confirmar` cria lançamento.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import func, select
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.erros import ErroApi, nao_encontrado
from app.esquemas.importacao import LinhaRascunho
from app.extensoes import db
from app.modelos import Anexo, Categoria, Importacao, Lancamento
from app.servicos import leitor_ia, pdf
from app.servicos.categorias import categoria_do_usuario
from app.servicos.tempo import fuso, hoje
from app.util import agora, dec, iso, num

log = logging.getLogger(__name__)

MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
MAX_TENTATIVAS = 3  # leituras pagas por documento (a 1ª + 2 "ler de novo")


def _assinatura_confere(conteudo: bytes, mime: str) -> bool:
    """O mime vem do navegador; os primeiros bytes dizem o que o arquivo é de verdade."""
    if mime == "application/pdf":
        return conteudo[:5] == b"%PDF-"
    if mime == "image/jpeg":
        return conteudo[:3] == b"\xff\xd8\xff"
    if mime == "image/png":
        return conteudo[:8] == b"\x89PNG\r\n\x1a\n"
    if mime == "image/webp":
        return conteudo[:4] == b"RIFF" and conteudo[8:12] == b"WEBP"
    return False


def _leitura_presa() -> timedelta:
    # Pior caso do SDK = 2 × timeout (max_retries=1 em leitor_ia); folga de 1 min.
    return timedelta(seconds=2 * current_app.config["ANTHROPIC_TIMEOUT"] + 60)


# ---------- consulta ----------

def buscar(uid: uuid.UUID, iid: uuid.UUID, travar: bool = False) -> Importacao:
    consulta = select(Importacao).where(Importacao.id == iid, Importacao.usuario_id == uid)
    if travar:
        consulta = consulta.with_for_update()
    imp = db.session.scalar(consulta)
    if imp is None:
        raise nao_encontrado("Importação")
    return imp


def listar(uid: uuid.UUID, limite: int = 30) -> list[Importacao]:
    return list(db.session.scalars(
        select(Importacao).where(Importacao.usuario_id == uid).order_by(Importacao.criado_em.desc()).limit(limite)
    ))


def caminho_arquivo(imp: Importacao) -> str:
    return os.path.join(current_app.config["UPLOAD_DIR"], imp.caminho)


def soltar_se_presa(imp: Importacao) -> None:
    """Worker reiniciado no meio da leitura deixa a importação em `lendo` para sempre."""
    if imp.estado == "lendo" and imp.atualizado_em and agora() - imp.atualizado_em > _leitura_presa():
        imp.estado = "erro"
        imp.erro = "A leitura demorou demais. Toque em “Ler de novo”."
        db.session.commit()


# ---------- criar ----------

def _usadas_no_mes(uid: uuid.UUID) -> int:
    inicio_local = datetime.combine(hoje().replace(day=1), datetime.min.time(), tzinfo=fuso())
    return db.session.scalar(
        select(func.count()).select_from(Importacao).where(
            Importacao.usuario_id == uid, Importacao.criado_em >= inicio_local.astimezone(timezone.utc)
        )
    ) or 0


def criar(uid: uuid.UUID, arquivo: FileStorage | None, forcar: bool = False) -> tuple[Importacao, Importacao | None]:
    """Valida e grava o original. Mesmo arquivo de novo = 409 (cada leitura custa), salvo `forcar`.

    Devolve (nova importação, importação anterior com o mesmo arquivo, se `forcar`)."""
    if not leitor_ia.configurado():
        raise ErroApi("IA_INDISPONIVEL", "A leitura de documentos por IA não está disponível agora.", 503)
    if arquivo is None or not arquivo.filename:
        raise ErroApi("VALIDACAO", "Envie o campo multipart 'arquivo'.", 422)
    mime = (arquivo.mimetype or "").lower()
    if mime not in MIMES:
        raise ErroApi("VALIDACAO", "Tipo de arquivo não permitido (jpg, png, webp ou pdf).", 422, {"tipo_mime": mime})
    conteudo = arquivo.read()
    if not conteudo:
        raise ErroApi("VALIDACAO", "Arquivo vazio.", 422)
    if len(conteudo) > current_app.config["MAX_CONTENT_LENGTH"]:
        raise ErroApi("ARQUIVO_GRANDE", "Arquivo excede 8 MB.", 413)
    if not _assinatura_confere(conteudo, mime):
        raise ErroApi("VALIDACAO", "O conteúdo do arquivo não é uma imagem ou PDF válido.", 422, {"tipo_mime": mime})

    limite = current_app.config["IMPORTACAO_LIMITE_MES"]
    if _usadas_no_mes(uid) >= limite:
        raise ErroApi("LIMITE_IMPORTACAO", f"Você já leu {limite} documentos este mês. O limite renova no dia 1º.", 429, {"limite": limite})

    sha = hashlib.sha256(conteudo).hexdigest()
    anterior = db.session.scalar(
        select(Importacao)
        .where(Importacao.usuario_id == uid, Importacao.sha256 == sha, Importacao.estado != "descartada")
        .order_by(Importacao.criado_em.desc())
        .limit(1)
    )
    if anterior is not None and not forcar:
        raise ErroApi(
            "IMPORTACAO_DUPLICADA", "Este arquivo já foi enviado.", 409,
            {"importacao_id": str(anterior.id), "criado_em": iso(anterior.criado_em), "estado": anterior.estado},
        )

    iid = uuid.uuid4()
    relativo = f"importacoes/{uid}/{iid}{MIMES[mime]}"
    destino = os.path.join(current_app.config["UPLOAD_DIR"], relativo)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "wb") as f:
        f.write(conteudo)

    imp = Importacao(
        id=iid, usuario_id=uid, estado="recebida",
        nome=(secure_filename(arquivo.filename)[:200] or f"{iid}{MIMES[mime]}"),
        tipo_mime=mime, tamanho=len(conteudo), sha256=sha, caminho=relativo,
    )
    db.session.add(imp)
    db.session.commit()
    return imp, anterior


# ---------- ler ----------

def _conteudo_para_leitura(imp: Importacao, senha: str | None) -> bytes | None:
    """PDF protegido → cópia aberta em memória. None = falta a senha (ou ela não abre)."""
    with open(caminho_arquivo(imp), "rb") as f:
        conteudo = f.read()
    if imp.tipo_mime != "application/pdf" or not pdf.esta_protegido(conteudo):
        return conteudo
    # Senha vazia abre o PDF que só restringe impressão/cópia: o usuário não precisa digitar nada.
    return pdf.abrir(conteudo, senha if senha is not None else "")


def disparar_leitura(imp: Importacao, senha: str | None = None) -> None:
    """Thread no gunicorn (o nginx corta em 60 s); inline nos testes.

    PDF com senha sem a senha certa: `senha` informada e errada dá 422; sem senha, a importação
    espera em `senha` (nada é cobrado). A senha nunca sai desta função: o que segue é a cópia aberta."""
    try:
        conteudo = _conteudo_para_leitura(imp, senha)
    except OSError as e:
        raise nao_encontrado("Arquivo original") from e
    if conteudo is None:
        if senha is not None:
            raise ErroApi("SENHA_INCORRETA", "Essa senha não abre o PDF. Confira e tente de novo.", 422)
        imp.estado = "senha"
        imp.erro = None
        db.session.commit()
        return
    imp.estado = "lendo"
    imp.erro = None
    imp.tentativas = (imp.tentativas or 0) + 1
    db.session.commit()
    app = current_app._get_current_object()
    if app.config.get("TESTING"):
        _ler(app, imp.id, conteudo)
        db.session.expire_all()
        return
    threading.Thread(target=_ler, args=(app, imp.id, conteudo), daemon=True).start()


def _categorias(uid: uuid.UUID) -> list[dict]:
    cats = db.session.scalars(
        select(Categoria).where(Categoria.usuario_id == uid, Categoria.arquivada.is_(False)).order_by(Categoria.ordem)
    )
    return [{"id": str(c.id), "nome": c.nome} for c in cats]


def _linha_do_rascunho(lida, categorias_validas: set[str], ref: date) -> dict:
    data = None
    if lida.data:
        try:
            data = date.fromisoformat(lida.data)
        except ValueError:
            data = None
    if data is not None and data > ref + timedelta(days=400):
        data = None  # ano lido errado: melhor o usuário escolher
    valor = dec(lida.valor_centavos / 100) if lida.valor_centavos and lida.valor_centavos > 0 else None
    return {
        "data": data.isoformat() if data else None,
        "valor": num(valor),
        "tipo": lida.tipo,
        "descricao": (lida.descricao or "").strip()[:200],
        "categoria_id": lida.categoria_id if lida.categoria_id in categorias_validas else None,
        "forma_pagamento": lida.forma_pagamento,
        "confianca": "baixa" if (data is None or valor is None) else lida.confianca,
        "incluir": valor is not None,
    }


def _ler(app, iid: uuid.UUID, conteudo: bytes) -> None:
    with app.app_context():
        try:
            imp = db.session.get(Importacao, iid)
            if imp is None or imp.estado != "lendo":
                return
            usuario, mime = imp.usuario_id, imp.tipo_mime
            db.session.commit()  # não segura transação aberta durante a chamada à IA
            novos: dict
            try:
                categorias = _categorias(usuario)
                ref = hoje()
                leitura = leitor_ia.ler_documento(conteudo, mime, categorias, ref)
                validas = {c["id"] for c in categorias}
                r = leitura.resultado
                novos = {
                    "estado": "revisar", "erro": None, "tipo_documento": r.tipo_documento,
                    "modelo_ia": leitura.modelo[:60], "tokens_entrada": leitura.tokens_entrada,
                    "tokens_saida": leitura.tokens_saida,
                    "resultado": {
                        "estabelecimento": r.estabelecimento,
                        "observacao": r.observacao,
                        "linhas": [_linha_do_rascunho(lida, validas, ref) for lida in r.linhas],
                    },
                }
            except leitor_ia.ErroLeitura as e:
                novos = {"estado": "erro", "erro": str(e)[:300]}
            except Exception:  # noqa: BLE001 — qualquer falha vira estado legível, nunca leitura presa
                log.exception("importacao %s: falha inesperada na leitura", iid)
                db.session.rollback()
                novos = {"estado": "erro", "erro": "Falha inesperada ao ler o documento. Tente ler de novo."}
            # Só grava se ninguém mexeu enquanto a IA lia (ex.: marcada como presa e relida).
            imp = db.session.scalar(select(Importacao).where(Importacao.id == iid).with_for_update())
            if imp is not None and imp.estado == "lendo":
                for campo, valor in novos.items():
                    setattr(imp, campo, valor)
            db.session.commit()
        finally:
            db.session.remove()


def reler(imp: Importacao) -> None:
    soltar_se_presa(imp)
    if imp.estado != "erro":
        raise ErroApi("ESTADO_INVALIDO", "Só dá para ler de novo um documento que falhou.", 409, {"estado": imp.estado})
    if (imp.tentativas or 0) >= MAX_TENTATIVAS:
        raise ErroApi("LIMITE_TENTATIVAS", f"Este documento já foi lido {MAX_TENTATIVAS} vezes. Envie uma foto mais nítida.", 429)
    if not leitor_ia.configurado():
        raise ErroApi("IA_INDISPONIVEL", "A leitura de documentos por IA não está disponível agora.", 503)
    disparar_leitura(imp)


def informar_senha(imp: Importacao, senha: str) -> None:
    if imp.estado != "senha":
        raise ErroApi("ESTADO_INVALIDO", "Este documento não está esperando senha.", 409, {"estado": imp.estado})
    if not senha or len(senha) > 128:
        raise ErroApi("VALIDACAO", "Informe a senha do PDF.", 422)
    if (imp.tentativas or 0) >= MAX_TENTATIVAS:
        raise ErroApi("LIMITE_TENTATIVAS", f"Este documento já foi lido {MAX_TENTATIVAS} vezes.", 429)
    if not leitor_ia.configurado():
        raise ErroApi("IA_INDISPONIVEL", "A leitura de documentos por IA não está disponível agora.", 503)
    disparar_leitura(imp, senha)


# ---------- revisar, confirmar, descartar ----------

def _linha_para_json(linha: LinhaRascunho) -> dict:
    return {
        "data": linha.data.isoformat() if linha.data else None,
        "valor": num(dec(linha.valor)) if linha.valor is not None else None,
        "tipo": linha.tipo,
        "descricao": linha.descricao,
        "categoria_id": str(linha.categoria_id) if linha.categoria_id else None,
        "forma_pagamento": linha.forma_pagamento,
        "confianca": linha.confianca,
        "incluir": linha.incluir,
    }


def atualizar_rascunho(imp: Importacao, linhas: list[LinhaRascunho], commit: bool = True) -> None:
    if imp.estado != "revisar":
        raise ErroApi("ESTADO_INVALIDO", "Só dá para editar uma importação em revisão.", 409, {"estado": imp.estado})
    for linha in linhas:
        if linha.categoria_id:
            categoria_do_usuario(imp.usuario_id, linha.categoria_id)
    imp.resultado = {**(imp.resultado or {}), "linhas": [_linha_para_json(l) for l in linhas]}
    if commit:
        db.session.commit()


def confirmar(imp: Importacao, linhas_editadas: list[LinhaRascunho] | None = None) -> list[Lancamento]:
    """Cria os lançamentos marcados numa transação. Confirmar de novo devolve os mesmos (idempotente).

    `linhas_editadas` (opcional) é o rascunho como está na tela: aplicado antes, na mesma trava."""
    if imp.estado == "concluida":
        ids = [uuid.UUID(i) for i in (imp.resultado or {}).get("lancamentos_criados", [])]
        return list(db.session.scalars(select(Lancamento).where(Lancamento.id.in_(ids)))) if ids else []
    if imp.estado != "revisar":
        raise ErroApi("ESTADO_INVALIDO", "Só dá para confirmar uma importação em revisão.", 409, {"estado": imp.estado})
    if linhas_editadas is not None:
        atualizar_rascunho(imp, linhas_editadas, commit=False)
    resultado = imp.resultado or {}

    linhas = [LinhaRascunho.model_validate(l) for l in resultado.get("linhas", [])]
    marcadas = [l for l in linhas if l.incluir]
    if not marcadas:
        raise ErroApi("VALIDACAO", "Marque pelo menos um lançamento para salvar.", 422)
    faltando = [i for i, l in enumerate(linhas) if l.incluir and (l.data is None or l.valor is None)]
    if faltando:
        raise ErroApi("VALIDACAO", "Preencha data e valor das linhas marcadas.", 422, {"linhas": faltando})

    criados = []
    for linha in marcadas:
        if linha.categoria_id:
            categoria_do_usuario(imp.usuario_id, linha.categoria_id)
        lanc = Lancamento(
            usuario_id=imp.usuario_id, tipo=linha.tipo, valor=dec(linha.valor), categoria_id=linha.categoria_id,
            descricao=linha.descricao or (resultado.get("estabelecimento") or "")[:200], data=linha.data,
            forma_pagamento=linha.forma_pagamento, importacao_id=imp.id,
        )
        # O original vira anexo do lançamento, apontando para o mesmo arquivo (sem cópia).
        lanc.anexos.append(Anexo(
            nome=imp.nome, tipo_mime=imp.tipo_mime, tamanho=imp.tamanho,
            armazenamento="importacao", importacao_id=imp.id,
        ))
        db.session.add(lanc)
        criados.append(lanc)
    db.session.flush()
    imp.resultado = {**resultado, "lancamentos_criados": [str(l.id) for l in criados]}
    imp.estado = "concluida"
    imp.concluida_em = agora()
    db.session.commit()
    return criados


def descartar(imp: Importacao) -> None:
    if imp.estado == "concluida":
        raise ErroApi("ESTADO_INVALIDO", "Esta importação já virou lançamentos; exclua os lançamentos se quiser.", 409)
    imp.estado = "descartada"
    db.session.commit()
