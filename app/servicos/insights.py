"""Insights automáticos: frases curtas, com número, geradas a partir dos dados da semana/mês.

Cada insight: {tipo, nivel ("bom" | "atencao" | "info"), titulo, detalhe, valor, categoria_id, link}.
Ordem de saída: atenção primeiro, depois bom, depois info. Máximo de 8.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.extensoes import db
from app.modelos import Categoria, ContaAgendada, OcorrenciaConta, PrecoHistorico, Usuario
from app.servicos import metricas
from app.servicos.contas import gerar_ocorrencias
from app.servicos.tempo import hoje, limites_mes, segunda_feira, dias_do_mes
from app.util import num

MINIMO_CATEGORIA = Decimal("20")   # ignora variações em categorias com menos que isso
VARIACAO_RELEVANTE = 25.0          # % para virar insight
MAX_INSIGHTS = 8


def _moeda(v: Decimal | float) -> str:
    v = float(v)
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _insight(tipo: str, nivel: str, titulo: str, detalhe: str, valor=None, categoria_id=None, link: str | None = None) -> dict:
    return {
        "tipo": tipo,
        "nivel": nivel,
        "titulo": titulo,
        "detalhe": detalhe,
        "valor": num(valor) if isinstance(valor, Decimal) else valor,
        "categoria_id": str(categoria_id) if categoria_id else None,
        "link": link,
    }


def _nomes_categorias(usuario_id: uuid.UUID) -> dict[uuid.UUID, str]:
    linhas = db.session.execute(select(Categoria.id, Categoria.nome).where(Categoria.usuario_id == usuario_id)).all()
    return {i: n for i, n in linhas}


def _variacao_categorias(usuario: Usuario, inicio: date, nomes: dict) -> list[dict]:
    fim = inicio + timedelta(days=6)
    atual = dict(metricas._por_categoria(usuario.id, inicio, fim))
    anterior = dict(metricas._por_categoria(usuario.id, inicio - timedelta(days=7), fim - timedelta(days=7)))
    saida = []
    for cat_id, total in atual.items():
        if cat_id is None:
            continue
        antes = anterior.get(cat_id, Decimal(0))
        if antes < MINIMO_CATEGORIA or total < MINIMO_CATEGORIA:
            continue
        pct = float((total - antes) / antes * 100)
        nome = nomes.get(cat_id, "Categoria")
        if pct >= VARIACAO_RELEVANTE:
            saida.append(_insight("categoria_subiu", "atencao", f"{nome} {pct:.0f}% acima da semana passada",
                                  f"{_moeda(total)} esta semana contra {_moeda(antes)} na anterior (+{_moeda(total - antes)}).",
                                  total - antes, cat_id, "/semana"))
        elif pct <= -VARIACAO_RELEVANTE:
            saida.append(_insight("categoria_caiu", "bom", f"{nome} {abs(pct):.0f}% abaixo da semana passada",
                                  f"{_moeda(total)} esta semana contra {_moeda(antes)} na anterior (−{_moeda(antes - total)}).",
                                  antes - total, cat_id, "/semana"))
    saida.sort(key=lambda i: -abs(i["valor"] or 0))
    return saida[:3]


def _precos_itens(usuario: Usuario, referencia: date) -> list[dict]:
    """Compara a última compra de cada item com a anterior (janela de 60 dias)."""
    desde = referencia - timedelta(days=60)
    linhas = db.session.execute(
        select(PrecoHistorico.descricao, PrecoHistorico.descricao_normalizada, PrecoHistorico.valor_unitario, PrecoHistorico.data)
        .where(PrecoHistorico.usuario_id == usuario.id, PrecoHistorico.data >= desde)
        .order_by(PrecoHistorico.descricao_normalizada, PrecoHistorico.data.desc(), PrecoHistorico.criado_em.desc())
    ).all()
    por_item: dict[str, list] = {}
    for descricao, norm, valor, data in linhas:
        por_item.setdefault(norm, []).append((descricao, valor, data))
    saida = []
    for norm, hist in por_item.items():
        if len(hist) < 2:
            continue
        (descricao, ultimo, data_u), (_, anterior, _) = hist[0], hist[1]
        if anterior <= 0:
            continue
        dif = ultimo - anterior
        pct = float(dif / anterior * 100)
        if abs(dif) < Decimal("0.50") or abs(pct) < 5:
            continue
        if dif > 0:
            saida.append(_insight("preco_subiu", "atencao", f"{descricao} está {_moeda(dif)} mais caro",
                                  f"{_moeda(ultimo)} na última compra ({data_u.strftime('%d/%m')}) contra {_moeda(anterior)} na anterior (+{pct:.0f}%).",
                                  dif, None, "/mercado"))
        else:
            saida.append(_insight("preco_caiu", "bom", f"{descricao} está {_moeda(-dif)} mais barato",
                                  f"{_moeda(ultimo)} na última compra ({data_u.strftime('%d/%m')}) contra {_moeda(anterior)} na anterior ({pct:.0f}%).",
                                  -dif, None, "/mercado"))
    saida.sort(key=lambda i: -(i["valor"] or 0))
    return saida[:3]


def _orcamentos_categoria(usuario: Usuario, referencia: date, nomes: dict) -> list[dict]:
    inicio, fim = limites_mes(referencia.year, referencia.month)
    gasto = dict(metricas._por_categoria(usuario.id, inicio, fim))
    orcamentos = db.session.execute(
        select(Categoria.id, Categoria.orcamento_mensal).where(Categoria.usuario_id == usuario.id, Categoria.orcamento_mensal.isnot(None), Categoria.arquivada.is_(False))
    ).all()
    saida = []
    for cat_id, orc in orcamentos:
        if not orc or orc <= 0:
            continue
        g = gasto.get(cat_id, Decimal(0))
        pct = float(g / orc * 100)
        nome = nomes.get(cat_id, "Categoria")
        dias_restantes = dias_do_mes(referencia.year, referencia.month) - referencia.day
        if pct > 100:
            saida.append(_insight("orcamento_estourou", "atencao", f"{nome} estourou o orçamento do mês",
                                  f"{_moeda(g)} de {_moeda(orc)} ({pct:.0f}%), e ainda faltam {dias_restantes} dias.", g - orc, cat_id, "/mes"))
        elif pct >= 85:
            saida.append(_insight("orcamento_perto", "atencao", f"{nome} já usou {pct:.0f}% do orçamento",
                                  f"Restam {_moeda(orc - g)} para {dias_restantes} dias.", orc - g, cat_id, "/mes"))
    return saida[:2]


def _projecao_mes(usuario: Usuario, referencia: date) -> list[dict]:
    if not usuario.orcamento_mensal or usuario.orcamento_mensal <= 0:
        return []
    inicio, fim = limites_mes(referencia.year, referencia.month)
    gasto = metricas._total(usuario.id, inicio, fim)
    decorridos = max(1, referencia.day)
    projecao = gasto / decorridos * dias_do_mes(referencia.year, referencia.month)
    if projecao > usuario.orcamento_mensal * Decimal("1.05") and referencia.day >= 5:
        return [_insight("projecao_acima", "atencao", f"No ritmo atual o mês fecha em {_moeda(projecao)}",
                         f"Seu orçamento é {_moeda(usuario.orcamento_mensal)}. Para caber, o restante do mês precisa ficar em "
                         f"{_moeda(max(Decimal(0), usuario.orcamento_mensal - gasto))}.", projecao - usuario.orcamento_mensal, None, "/mes")]
    if referencia.day >= 10 and projecao <= usuario.orcamento_mensal * Decimal("0.9"):
        return [_insight("projecao_dentro", "bom", f"Mês projetado em {_moeda(projecao)}, dentro do orçamento",
                         f"Folga de {_moeda(usuario.orcamento_mensal - projecao)} se mantiver o ritmo.", usuario.orcamento_mensal - projecao, None, "/mes")]
    return []


def _contas(usuario: Usuario, referencia: date) -> list[dict]:
    gerar_ocorrencias(usuario.id, referencia.year, referencia.month)
    linhas = db.session.execute(
        select(OcorrenciaConta, ContaAgendada)
        .join(ContaAgendada, ContaAgendada.id == OcorrenciaConta.conta_id)
        .where(ContaAgendada.usuario_id == usuario.id, OcorrenciaConta.status != "paga")
        .order_by(OcorrenciaConta.vencimento)
    ).all()
    atrasadas = [(o, c) for o, c in linhas if o.vencimento < referencia]
    vencendo = [(o, c) for o, c in linhas if referencia <= o.vencimento <= referencia + timedelta(days=max(1, c.lembrete_dias or 3))]
    saida = []
    if atrasadas:
        total = sum((o.valor_real or c.valor_estimado or Decimal(0)) for o, c in atrasadas)
        nomes = ", ".join(c.nome for _, c in atrasadas[:3])
        saida.append(_insight("contas_atrasadas", "atencao", f"{len(atrasadas)} conta{'s' if len(atrasadas) > 1 else ''} atrasada{'s' if len(atrasadas) > 1 else ''}",
                              f"{nomes} — {_moeda(total)} no total.", total, None, "/contas"))
    if vencendo:
        total = sum((o.valor_real or c.valor_estimado or Decimal(0)) for o, c in vencendo)
        o0, c0 = vencendo[0]
        quando = "hoje" if o0.vencimento == referencia else f"dia {o0.vencimento.day}"
        saida.append(_insight("contas_vencendo", "info", f"{c0.nome} vence {quando}" if len(vencendo) == 1 else f"{len(vencendo)} contas vencem nos próximos dias",
                              f"{_moeda(total)} a pagar" + (f" — {', '.join(c.nome for _, c in vencendo[:3])}" if len(vencendo) > 1 else ""), total, None, "/contas"))
    return saida


def gerar(usuario: Usuario, inicio: date | None = None) -> dict:
    referencia = hoje()
    inicio = segunda_feira(inicio or referencia)
    nomes = _nomes_categorias(usuario.id)
    fim = inicio + timedelta(days=6)

    itens: list[dict] = []
    itens += _contas(usuario, referencia)
    itens += _orcamentos_categoria(usuario, referencia, nomes)
    itens += _projecao_mes(usuario, referencia)
    itens += _variacao_categorias(usuario, inicio, nomes)
    itens += _precos_itens(usuario, referencia)

    total_semana = metricas._total(usuario.id, inicio, fim)
    if total_semana == 0:
        itens.append(_insight("sem_gastos", "info", "Nenhum gasto registrado esta semana",
                              "Abra o Modo Mercado na próxima compra ou lance um gasto em menos de 10 segundos.", None, None, "/mercado"))
    else:
        semana = metricas.semanal(usuario, inicio)
        if semana["semana_mais_cara_do_mes"] and referencia.day > 7:
            itens.append(_insight("semana_mais_cara", "info", "Esta é a semana mais cara do mês até agora",
                                  f"{_moeda(total_semana)} — o dia mais caro foi {semana['dia_mais_caro'][8:10]}/{semana['dia_mais_caro'][5:7]}.", total_semana, None, "/semana"))

    ordem = {"atencao": 0, "bom": 1, "info": 2}
    itens.sort(key=lambda i: ordem[i["nivel"]])
    return {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "dados": itens[:MAX_INSIGHTS]}
