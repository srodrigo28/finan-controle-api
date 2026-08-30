"""Métricas diária, semanal e mensal."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.extensoes import db
from app.modelos import Categoria, Lancamento, OcorrenciaConta, ContaAgendada, Usuario
from app.servicos.contas import gerar_ocorrencias
from app.servicos.tempo import dias_do_mes, hoje, limites_mes, mes_anterior, segunda_feira, semanas_do_mes
from app.util import data_iso, num

ZERO = Decimal("0.00")


def _total(usuario_id: uuid.UUID, de: date, ate: date, tipo: str = "despesa") -> Decimal:
    valor = db.session.scalar(
        select(func.coalesce(func.sum(Lancamento.valor), 0)).where(
            Lancamento.usuario_id == usuario_id,
            Lancamento.tipo == tipo,
            Lancamento.data >= de,
            Lancamento.data <= ate,
        )
    )
    return Decimal(valor or 0).quantize(Decimal("0.01"))


def _por_categoria(usuario_id: uuid.UUID, de: date, ate: date) -> list[tuple[uuid.UUID | None, Decimal]]:
    linhas = db.session.execute(
        select(Lancamento.categoria_id, func.sum(Lancamento.valor))
        .where(
            Lancamento.usuario_id == usuario_id,
            Lancamento.tipo == "despesa",
            Lancamento.data >= de,
            Lancamento.data <= ate,
        )
        .group_by(Lancamento.categoria_id)
        .order_by(func.sum(Lancamento.valor).desc())
    ).all()
    return [(cid, Decimal(t).quantize(Decimal("0.01"))) for cid, t in linhas]


def _por_dia(usuario_id: uuid.UUID, de: date, ate: date) -> dict[date, Decimal]:
    linhas = db.session.execute(
        select(Lancamento.data, func.sum(Lancamento.valor))
        .where(
            Lancamento.usuario_id == usuario_id,
            Lancamento.tipo == "despesa",
            Lancamento.data >= de,
            Lancamento.data <= ate,
        )
        .group_by(Lancamento.data)
    ).all()
    return {d: Decimal(t).quantize(Decimal("0.01")) for d, t in linhas}


def _pct(parte: Decimal, todo: Decimal) -> float:
    return 0.0 if todo == 0 else round(float(parte / todo * 100), 1)


def diario(usuario: Usuario, dia: date) -> dict:
    despesas = _total(usuario.id, dia, dia, "despesa")
    receitas = _total(usuario.id, dia, dia, "receita")
    orcamento_diario = usuario.orcamento_diario
    if orcamento_diario is None and usuario.orcamento_mensal is not None:
        orcamento_diario = (usuario.orcamento_mensal / dias_do_mes(dia.year, dia.month)).quantize(Decimal("0.01"))
    lancamentos = db.session.scalars(
        select(Lancamento)
        .where(Lancamento.usuario_id == usuario.id, Lancamento.data == dia)
        .order_by(Lancamento.criado_em.desc())
    ).all()
    return {
        "data": data_iso(dia),
        "total_despesas": num(despesas),
        "total_receitas": num(receitas),
        "orcamento_diario": num(orcamento_diario),
        "saldo_orcamento": num(orcamento_diario - despesas) if orcamento_diario is not None else None,
        "por_categoria": [{"categoria_id": str(c) if c else None, "total": num(t)} for c, t in _por_categoria(usuario.id, dia, dia)],
        "lancamentos": [lc.para_dict() for lc in lancamentos],
    }


def semanal(usuario: Usuario, inicio: date) -> dict:
    inicio = segunda_feira(inicio)
    fim = inicio + timedelta(days=6)
    total = _total(usuario.id, inicio, fim)
    total_anterior = _total(usuario.id, inicio - timedelta(days=7), fim - timedelta(days=7))
    dias = _por_dia(usuario.id, inicio, fim)
    por_dia = [{"data": data_iso(inicio + timedelta(days=i)), "total": num(dias.get(inicio + timedelta(days=i), ZERO))} for i in range(7)]
    dia_mais_caro = max(por_dia, key=lambda d: d["total"])["data"] if total > 0 else None

    # Semana mais cara do mês da data `inicio`: compara com as demais semanas que tocam o mesmo mês.
    totais_semanas = [_total(usuario.id, s, f) for s, f in semanas_do_mes(inicio.year, inicio.month)]
    mais_cara = total > 0 and total >= max(totais_semanas, default=ZERO)

    variacao_valor = total - total_anterior
    return {
        "inicio": data_iso(inicio),
        "fim": data_iso(fim),
        "total": num(total),
        "total_anterior": num(total_anterior),
        "variacao_valor": num(variacao_valor),
        "variacao_pct": _pct(variacao_valor, total_anterior) if total_anterior > 0 else None,
        "por_dia": por_dia,
        "por_categoria": [
            {"categoria_id": str(c) if c else None, "total": num(t), "pct": _pct(t, total)}
            for c, t in _por_categoria(usuario.id, inicio, fim)
        ],
        "dia_mais_caro": dia_mais_caro,
        "semana_mais_cara_do_mes": bool(mais_cara),
    }


def mensal(usuario: Usuario, ano: int, mes: int) -> dict:
    inicio, fim = limites_mes(ano, mes)
    despesas = _total(usuario.id, inicio, fim, "despesa")
    receitas = _total(usuario.id, inicio, fim, "receita")

    anteriores = []
    a, m = ano, mes
    for _ in range(5):
        a, m = mes_anterior(a, m)
        i, f = limites_mes(a, m)
        anteriores.append({"mes": f"{a:04d}-{m:02d}", "total": num(_total(usuario.id, i, f))})
    anteriores.reverse()

    orcamentos = {
        c.id: c.orcamento_mensal
        for c in db.session.scalars(select(Categoria).where(Categoria.usuario_id == usuario.id)).all()
    }
    por_categoria = []
    for cid, t in _por_categoria(usuario.id, inicio, fim):
        orc = orcamentos.get(cid)
        por_categoria.append({
            "categoria_id": str(cid) if cid else None,
            "total": num(t),
            "orcamento": num(orc),
            "pct_orcamento": _pct(t, orc) if orc else None,
        })

    ocorrencias = gerar_ocorrencias(usuario.id, ano, mes)
    pagas = [o for o in ocorrencias if o.status == "paga"]
    pendentes = [o for o in ocorrencias if o.status != "paga"]
    total_pendente = sum((o.conta.valor_estimado or ZERO for o in pendentes), ZERO)

    h = hoje()
    if (ano, mes) == (h.year, h.month):
        dias_decorridos = max(h.day, 1)
        projecao = (despesas / dias_decorridos * dias_do_mes(ano, mes)).quantize(Decimal("0.01"))
    elif (ano, mes) < (h.year, h.month):
        projecao = despesas
    else:
        projecao = ZERO

    semanas = [{"inicio": data_iso(s), "fim": data_iso(f), "total": num(_total(usuario.id, s, f))} for s, f in semanas_do_mes(ano, mes)]

    return {
        "mes": f"{ano:04d}-{mes:02d}",
        "total_despesas": num(despesas),
        "total_receitas": num(receitas),
        "saldo": num(receitas - despesas),
        "orcamento_mensal": num(usuario.orcamento_mensal),
        "meses_anteriores": anteriores,
        "por_categoria": por_categoria,
        "contas": {"pagas": len(pagas), "pendentes": len(pendentes), "total_pendente": num(total_pendente)},
        "projecao_fechamento": num(projecao),
        "semanas": semanas,
    }
