"""Central de notificações do app (o sino).

O motor de insights (`servicos/insights.py`) recalcula tudo a cada chamada e não guarda estado — por
isso um aviso ali não tem identidade e "marcar como lida" não existiria. Aqui cada aviso ganha uma
`chave` determinística e vira linha no banco:

- chave nova            → cria (entra na fila, não lida)
- chave que já existe   → atualiza título/corpo (o texto muda: "2 contas atrasadas" → "3")
- chave que sumiu       → marca `resolvida_em` (N5a: a conta foi paga, o aviso sai da fila sozinho)

Nada é apagado: a linha fica como histórico, com `lida_em` e `resolvida_em` preenchidos.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.extensoes import db
from app.modelos import Notificacao, Usuario
from app.servicos import insights
from app.servicos.tempo import hoje

ORDEM_NIVEL = {"atencao": 0, "bom": 1, "info": 2}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def chave_do_insight(item: dict) -> str:
    """Identidade estável de um aviso.

    Inclui a competência para que o mesmo alerta em meses diferentes seja outro aviso — "orçamento
    estourado" de agosto não deve reaparecer como lido em setembro.
    """
    partes = [item["tipo"], item.get("categoria_id") or "", hoje().strftime("%Y-%m")]
    return ":".join(partes)


def sincronizar(usuario: Usuario) -> list[Notificacao]:
    """Reconcilia a fila com o que o motor de insights diz agora. Devolve a fila aberta."""
    gerados = insights.gerar(usuario)["dados"]
    por_chave = {chave_do_insight(i): i for i in gerados}

    existentes = {
        n.chave: n
        for n in db.session.scalars(select(Notificacao).where(Notificacao.usuario_id == usuario.id)).all()
    }

    for chave, item in por_chave.items():
        atual = existentes.get(chave)
        if atual is None:
            db.session.add(
                Notificacao(
                    usuario_id=usuario.id,
                    chave=chave,
                    tipo=item["tipo"],
                    nivel=item["nivel"],
                    titulo=item["titulo"],
                    corpo=item.get("detalhe"),
                    link=item.get("link"),
                )
            )
            continue
        # O aviso voltou a valer (ex.: atrasou de novo): reabre e volta a contar como não lida.
        if atual.resolvida_em is not None:
            atual.resolvida_em = None
            atual.lida_em = None
        atual.nivel = item["nivel"]
        atual.titulo = item["titulo"]
        atual.corpo = item.get("detalhe")
        atual.link = item.get("link")

    for chave, n in existentes.items():
        if chave not in por_chave and n.resolvida_em is None:
            n.resolvida_em = _agora()

    db.session.flush()
    return fila(usuario.id)


def fila(usuario_id: uuid.UUID) -> list[Notificacao]:
    """O que o sino mostra: o que ainda vale, atenção primeiro."""
    abertas = db.session.scalars(
        select(Notificacao).where(Notificacao.usuario_id == usuario_id, Notificacao.resolvida_em.is_(None))
    ).all()
    return sorted(abertas, key=lambda n: (ORDEM_NIVEL.get(n.nivel, 3), n.criado_em), reverse=False)


def nao_lidas(usuario_id: uuid.UUID) -> int:
    return sum(1 for n in fila(usuario_id) if n.lida_em is None)


def marcar_lida(notificacao: Notificacao) -> None:
    if notificacao.lida_em is None:
        notificacao.lida_em = _agora()
    db.session.flush()


def marcar_todas_lidas(usuario_id: uuid.UUID) -> int:
    agora = _agora()
    pendentes = [n for n in fila(usuario_id) if n.lida_em is None]
    for n in pendentes:
        n.lida_em = agora
    db.session.flush()
    return len(pendentes)
