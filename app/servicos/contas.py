"""Contas agendadas: geração de ocorrências por competência e pagamento."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.erros import ErroApi
from app.extensoes import db
from app.modelos import ContaAgendada, Lancamento, OcorrenciaConta
from app.servicos.tempo import dia_seguro, hoje, limites_mes
from app.util import data_iso, dec


def buscar_conta(usuario_id: uuid.UUID, conta_id: uuid.UUID) -> ContaAgendada:
    conta = db.session.get(ContaAgendada, conta_id)
    if conta is None or conta.usuario_id != usuario_id:
        raise ErroApi("NAO_ENCONTRADO", "Conta não encontrada.", 404)
    return conta


def buscar_ocorrencia(usuario_id: uuid.UUID, ocorrencia_id: uuid.UUID) -> OcorrenciaConta:
    oc = db.session.get(OcorrenciaConta, ocorrencia_id)
    if oc is None or oc.conta.usuario_id != usuario_id:
        raise ErroApi("NAO_ENCONTRADO", "Ocorrência não encontrada.", 404)
    return oc


def vencimentos_na_competencia(conta: ContaAgendada, ano: int, mes: int) -> list[date]:
    """Datas de vencimento que a conta gera dentro da competência."""
    inicio, fim = limites_mes(ano, mes)
    if conta.recorrencia == "mensal":
        return [dia_seguro(ano, mes, conta.dia_vencimento)]
    if conta.recorrencia == "semanal":
        # dia_vencimento aqui é o dia da semana (1=segunda … 7=domingo)
        alvo = max(1, min(conta.dia_vencimento, 7)) - 1
        d = inicio + timedelta(days=(alvo - inicio.weekday()) % 7)
        datas = []
        while d <= fim:
            datas.append(d)
            d += timedelta(days=7)
        return datas
    if conta.recorrencia == "anual":
        if conta.mes_referencia == mes:
            return [dia_seguro(ano, mes, conta.dia_vencimento)]
        return []
    if conta.recorrencia == "unica":
        if conta.mes_referencia == mes and (conta.ano_referencia in (None, ano)):
            return [dia_seguro(ano, mes, conta.dia_vencimento)]
        return []
    return []


def gerar_ocorrencias(usuario_id: uuid.UUID, ano: int, mes: int) -> list[OcorrenciaConta]:
    """Cria as ocorrências que faltam para a competência e devolve todas (ordenadas por vencimento)."""
    competencia = f"{ano:04d}-{mes:02d}"
    contas = db.session.scalars(
        select(ContaAgendada).where(ContaAgendada.usuario_id == usuario_id, ContaAgendada.ativa.is_(True))
    ).all()
    ja_existem = db.session.scalars(
        select(OcorrenciaConta)
        .join(ContaAgendada)
        .where(ContaAgendada.usuario_id == usuario_id, OcorrenciaConta.competencia == competencia)
    ).all()
    por_vencimento = {(o.conta_id, o.vencimento) for o in ja_existem}
    com_ocorrencia = {o.conta_id for o in ja_existem}
    for conta in contas:
        # Semanal gera várias por mês (dedupe por data). As demais geram uma só: se a competência
        # já tem a ocorrência, não recriar — senão adiar o vencimento faria voltar a data antiga.
        if conta.recorrencia != "semanal" and conta.id in com_ocorrencia:
            continue
        for venc in vencimentos_na_competencia(conta, ano, mes):
            if (conta.id, venc) not in por_vencimento:
                db.session.add(OcorrenciaConta(conta_id=conta.id, competencia=competencia, vencimento=venc))
    db.session.flush()

    # Só contas ativas: conta arquivada some do mês (as ocorrências ficam guardadas para o histórico).
    return db.session.scalars(
        select(OcorrenciaConta)
        .join(ContaAgendada)
        .where(
            ContaAgendada.usuario_id == usuario_id,
            ContaAgendada.ativa.is_(True),
            OcorrenciaConta.competencia == competencia,
        )
        .order_by(OcorrenciaConta.vencimento, ContaAgendada.nome)
    ).all()


def pagar_ocorrencia(
    usuario_id: uuid.UUID,
    ocorrencia: OcorrenciaConta,
    valor_real: Decimal,
    data: date | None,
    forma_pagamento: str | None,
) -> Lancamento:
    """Marca como paga e gera o lançamento do dia."""
    if ocorrencia.status == "paga":
        raise ErroApi("CONFLITO", "Ocorrência já está paga.", 409)
    conta = ocorrencia.conta
    lancamento = Lancamento(
        usuario_id=usuario_id,
        tipo="despesa",
        valor=dec(valor_real),
        categoria_id=conta.categoria_id,
        descricao=f"{conta.nome} ({ocorrencia.competencia})",
        data=data or hoje(),
        forma_pagamento=forma_pagamento or "boleto",
        conta_id=conta.id,
    )
    db.session.add(lancamento)
    db.session.flush()
    ocorrencia.valor_real = dec(valor_real)
    ocorrencia.status = "paga"
    ocorrencia.lancamento_id = lancamento.id
    db.session.flush()
    return lancamento


def realinhar_ocorrencias(conta: ContaAgendada) -> int:
    """Mudou o dia/recorrência: descarta os vencimentos futuros ainda pendentes para o gerador
    recriá-los na data nova. Pagas ficam (são histórico) e puladas também (decisão do usuário)."""
    h = hoje()
    competencia_atual = f"{h.year:04d}-{h.month:02d}"
    alvo = db.session.scalars(
        select(OcorrenciaConta).where(
            OcorrenciaConta.conta_id == conta.id,
            OcorrenciaConta.status == "pendente",
            OcorrenciaConta.competencia >= competencia_atual,
        )
    ).all()
    for oc in alvo:
        db.session.delete(oc)
    db.session.flush()
    return len(alvo)


def resumo_conta(conta: ContaAgendada) -> dict:
    """Números que a tela de detalhe usa para decidir o tom das ações (arquivar × excluir)."""
    ocorrencias = db.session.scalars(
        select(OcorrenciaConta).where(OcorrenciaConta.conta_id == conta.id)
    ).all()
    pagas = [o for o in ocorrencias if o.status == "paga"]
    ultima = max(pagas, key=lambda o: o.vencimento, default=None)
    total_pago = sum((o.valor_real or 0) for o in pagas)
    return {
        "ocorrencias_total": len(ocorrencias),
        "pagas": len(pagas),
        "total_pago": float(total_pago),
        "media_paga": float(total_pago / len(pagas)) if pagas else None,
        "ultimo_pagamento": data_iso(ultima.vencimento) if ultima else None,
    }


def excluir_conta(conta: ContaAgendada) -> None:
    """Apaga a conta e suas ocorrências. Os lançamentos já pagos ficam: a FK é ON DELETE SET NULL."""
    db.session.delete(conta)
    db.session.flush()


def reabrir_ocorrencia(ocorrencia: OcorrenciaConta) -> None:
    """Desfaz o pagamento: remove o lançamento gerado e volta para pendente."""
    if ocorrencia.lancamento_id:
        lanc = db.session.get(Lancamento, ocorrencia.lancamento_id)
        if lanc is not None:
            db.session.delete(lanc)
    ocorrencia.lancamento_id = None
    ocorrencia.valor_real = None
    ocorrencia.status = "pendente"
    db.session.flush()
