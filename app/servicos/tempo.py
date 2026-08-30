"""Datas no fuso do usuário (fixo em America/Sao_Paulo no MVP)."""
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app


def fuso() -> ZoneInfo:
    return ZoneInfo(current_app.config.get("FUSO_HORARIO", "America/Sao_Paulo"))


def hoje() -> date:
    return datetime.now(fuso()).date()


def segunda_feira(d: date) -> date:
    return d - timedelta(days=d.weekday())


def dias_do_mes(ano: int, mes: int) -> int:
    return monthrange(ano, mes)[1]


def limites_mes(ano: int, mes: int) -> tuple[date, date]:
    return date(ano, mes, 1), date(ano, mes, dias_do_mes(ano, mes))


def parse_mes(valor: str | None) -> tuple[int, int]:
    """'YYYY-MM' → (ano, mes). Sem valor → mês atual."""
    if not valor:
        h = hoje()
        return h.year, h.month
    try:
        ano, mes = valor.split("-")
        ano_i, mes_i = int(ano), int(mes)
        if not 1 <= mes_i <= 12:
            raise ValueError
        return ano_i, mes_i
    except ValueError:
        from app.erros import ErroApi

        raise ErroApi("VALIDACAO", "mes deve estar no formato YYYY-MM.", 422)


def mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


def semanas_do_mes(ano: int, mes: int) -> list[tuple[date, date]]:
    """Semanas (segunda→domingo) que tocam o mês."""
    inicio_mes, fim_mes = limites_mes(ano, mes)
    seg = segunda_feira(inicio_mes)
    semanas = []
    while seg <= fim_mes:
        semanas.append((seg, seg + timedelta(days=6)))
        seg += timedelta(days=7)
    return semanas


def dia_seguro(ano: int, mes: int, dia: int) -> date:
    """Dia do vencimento limitado ao último dia do mês (ex.: 31 em fevereiro → 28/29)."""
    return date(ano, mes, min(dia, dias_do_mes(ano, mes)))
