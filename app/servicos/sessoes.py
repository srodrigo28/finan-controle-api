"""Modo Mercado: fechamento de sessão e sincronização offline."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.erros import ErroApi
from app.esquemas.sessao import SessaoSincronizacao
from app.extensoes import db
from app.modelos import Categoria, ItemCompra, Lancamento, PrecoHistorico, SessaoCompra
from app.servicos.categorias import categoria_do_usuario
from app.servicos.tempo import hoje
from app.util import agora, dec, normalizar_descricao


def buscar_sessao(usuario_id: uuid.UUID, sessao_id: uuid.UUID) -> SessaoCompra:
    sessao = db.session.get(SessaoCompra, sessao_id)
    if sessao is None or sessao.usuario_id != usuario_id:
        raise ErroApi("NAO_ENCONTRADO", "Sessão não encontrada.", 404)
    return sessao


def _categoria_mercado(usuario_id: uuid.UUID) -> uuid.UUID | None:
    cat = db.session.scalar(
        select(Categoria)
        .where(Categoria.usuario_id == usuario_id, Categoria.pai_id.is_(None), Categoria.nome.ilike("mercado"))
        .limit(1)
    )
    return cat.id if cat else None


def fechar_sessao(
    sessao: SessaoCompra,
    usuario_id: uuid.UUID,
    total_pago: Decimal | None,
    motivo_divergencia: str | None = None,
    categoria_id: uuid.UUID | None = None,
    forma_pagamento: str | None = None,
    fechada_em: datetime | None = None,
) -> Lancamento:
    """Fecha a sessão: gera UM lançamento e grava o histórico de preço dos itens."""
    if sessao.status == "fechada" and sessao.lancamento_id:
        raise ErroApi("CONFLITO", "Sessão já está fechada.", 409)

    total_carrinho = sessao.calcular_total()
    total_pago = dec(total_pago) if total_pago is not None else total_carrinho
    categoria_do_usuario(usuario_id, categoria_id)
    categoria_final = categoria_id or _categoria_mercado(usuario_id)
    quando = fechada_em or agora()
    data = quando.astimezone(timezone.utc).date() if fechada_em else hoje()

    descricao = f"Mercado — {sessao.local}" if sessao.local else "Compra de mercado"
    lancamento = Lancamento(
        usuario_id=usuario_id,
        tipo="despesa",
        valor=total_pago,
        categoria_id=categoria_final,
        descricao=descricao,
        data=data,
        forma_pagamento=forma_pagamento,
        sessao_id=sessao.id,
    )
    db.session.add(lancamento)
    db.session.flush()

    sessao.status = "fechada"
    sessao.fechada_em = quando
    sessao.total_carrinho = total_carrinho
    sessao.total_pago = total_pago
    sessao.motivo_divergencia = motivo_divergencia if total_pago != total_carrinho else None
    sessao.lancamento_id = lancamento.id

    for item in sessao.itens:
        if item.removido:
            continue
        db.session.add(
            PrecoHistorico(
                usuario_id=usuario_id,
                descricao=item.descricao,
                descricao_normalizada=normalizar_descricao(item.descricao),
                categoria_id=item.categoria_id,
                valor_unitario=item.valor_unitario,
                data=data,
                sessao_id=sessao.id,
            )
        )
    db.session.flush()
    return lancamento


def _mais_recente(cliente: datetime | None, servidor: datetime | None) -> bool:
    """True se a versão do cliente deve vencer (último atualizado_em vence; sem carimbo = vence)."""
    if cliente is None:
        return True
    if servidor is None:
        return True
    if cliente.tzinfo is None:
        cliente = cliente.replace(tzinfo=timezone.utc)
    if servidor.tzinfo is None:
        servidor = servidor.replace(tzinfo=timezone.utc)
    return cliente >= servidor


def sincronizar_sessoes(usuario_id: uuid.UUID, sessoes: list[SessaoSincronizacao]) -> list[SessaoCompra]:
    """Upsert idempotente das sessões vindas do cliente offline."""
    resultado: list[SessaoCompra] = []
    for dados in sessoes:
        sessao = db.session.get(SessaoCompra, dados.id)
        if sessao is not None and sessao.usuario_id != usuario_id:
            raise ErroApi("PROIBIDO", "Sessão pertence a outro usuário.", 403, {"sessao_id": str(dados.id)})

        if sessao is None:
            sessao = SessaoCompra(
                id=dados.id,
                usuario_id=usuario_id,
                local=dados.local,
                orcamento=dados.orcamento,
                status="aberta",
                aberta_em=dados.aberta_em or agora(),
            )
            db.session.add(sessao)
            db.session.flush()
        elif sessao.status == "aberta" and _mais_recente(dados.atualizado_em, sessao.atualizado_em):
            sessao.local = dados.local
            sessao.orcamento = dados.orcamento

        # Itens: upsert por id, último atualizado_em vence. Sessão já fechada é imutável.
        if sessao.status == "aberta":
            existentes = {i.id: i for i in sessao.itens}
            for it in dados.itens:
                categoria_do_usuario(usuario_id, it.categoria_id)
                atual = existentes.get(it.id)
                if atual is None:
                    novo = ItemCompra(
                        id=it.id,
                        sessao_id=sessao.id,
                        descricao=it.descricao,
                        categoria_id=it.categoria_id,
                        valor_unitario=dec(it.valor_unitario),
                        quantidade=dec(it.quantidade, 3),
                        removido=it.removido,
                    )
                    if it.criado_em:
                        novo.criado_em = it.criado_em
                    db.session.add(novo)
                    sessao.itens.append(novo)
                elif _mais_recente(it.atualizado_em, atual.atualizado_em):
                    atual.descricao = it.descricao
                    atual.categoria_id = it.categoria_id
                    atual.valor_unitario = dec(it.valor_unitario)
                    atual.quantidade = dec(it.quantidade, 3)
                    atual.removido = it.removido
            db.session.flush()
            db.session.refresh(sessao)

            if dados.status == "fechada" and sessao.lancamento_id is None:
                fechar_sessao(
                    sessao,
                    usuario_id,
                    dados.total_pago,
                    dados.motivo_divergencia,
                    dados.categoria_id,
                    dados.forma_pagamento,
                    fechada_em=dados.fechada_em,
                )
            elif dados.status == "abandonada":
                sessao.status = "abandonada"
                sessao.fechada_em = dados.fechada_em or agora()
                sessao.total_carrinho = sessao.calcular_total()

        db.session.flush()
        db.session.refresh(sessao)
        resultado.append(sessao)
    return resultado
