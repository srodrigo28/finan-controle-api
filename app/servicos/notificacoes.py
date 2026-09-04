"""Web Push (VAPID) — lembretes de vencimento e testes. Básico e sem fila: envia na hora."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app
from pywebpush import WebPushException, webpush
from sqlalchemy import select

from app.extensoes import db
from app.modelos import ContaAgendada, InscricaoPush, OcorrenciaConta, Usuario
from app.servicos.contas import gerar_ocorrencias
from app.servicos.tempo import hoje

log = logging.getLogger(__name__)


def configurado() -> bool:
    cfg = current_app.config
    return bool(cfg.get("VAPID_PUBLIC_KEY") and cfg.get("VAPID_PRIVATE_KEY"))


def _moeda(v) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def enviar_para_inscricao(insc: InscricaoPush, titulo: str, corpo: str, url: str = "/inicio", tag: str | None = None) -> bool:
    """Envia um push. Assinatura morta (404/410) é removida. Devolve True se o push saiu."""
    cfg = current_app.config
    payload = json.dumps({"titulo": titulo, "corpo": corpo, "url": url, "tag": tag or "finan"})
    try:
        webpush(
            subscription_info=insc.como_assinatura(),
            data=payload,
            vapid_private_key=cfg["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": cfg.get("VAPID_SUBJECT", "mailto:contato@99dev.pro")},
            ttl=60 * 60 * 12,
        )
        insc.ultimo_envio_em = datetime.now(timezone.utc)
        insc.ultimo_erro = None
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        insc.ultimo_erro = f"{status}: {str(exc)[:150]}"
        if status in (404, 410):
            log.info("push: assinatura expirada removida (%s)", insc.id)
            db.session.delete(insc)
        else:
            log.warning("push falhou (%s): %s", status, exc)
        return False


def enviar_para_usuario(usuario_id: uuid.UUID, titulo: str, corpo: str, url: str = "/inicio", tag: str | None = None) -> int:
    inscricoes = db.session.execute(select(InscricaoPush).where(InscricaoPush.usuario_id == usuario_id)).scalars().all()
    enviados = sum(1 for i in inscricoes if enviar_para_inscricao(i, titulo, corpo, url, tag))
    db.session.commit()
    return enviados


def lembretes_de_vencimento() -> dict:
    """Roda uma vez por dia (cron). Para cada usuário com push: contas atrasadas ou vencendo dentro de `lembrete_dias`."""
    ref = hoje()
    usuarios = db.session.execute(
        select(Usuario).where(Usuario.id.in_(select(InscricaoPush.usuario_id).distinct()))
    ).scalars().all()
    resumo = {"usuarios": 0, "enviados": 0, "sem_pendencia": 0}
    for u in usuarios:
        gerar_ocorrencias(u.id, ref.year, ref.month)
        linhas = db.session.execute(
            select(OcorrenciaConta, ContaAgendada)
            .join(ContaAgendada, ContaAgendada.id == OcorrenciaConta.conta_id)
            .where(
                ContaAgendada.usuario_id == u.id,
                ContaAgendada.ativa.is_(True),
                OcorrenciaConta.status.not_in(("paga", "pulada")),
            )
            .order_by(OcorrenciaConta.vencimento)
        ).all()
        atrasadas = [(o, c) for o, c in linhas if o.vencimento < ref]
        vencendo = [(o, c) for o, c in linhas if ref <= o.vencimento <= ref + timedelta(days=max(1, c.lembrete_dias or 3))]
        if not atrasadas and not vencendo:
            resumo["sem_pendencia"] += 1
            continue
        resumo["usuarios"] += 1
        if vencendo:
            o, c = vencendo[0]
            valor = o.valor_real or c.valor_estimado or 0
            if o.vencimento == ref:
                quando = "hoje"
            elif o.vencimento == ref + timedelta(days=1):
                quando = "amanhã"
            else:
                quando = f"dia {o.vencimento.day}"
            if len(vencendo) == 1:
                titulo, corpo = f"{c.nome} vence {quando}", f"{_moeda(valor)} — toque para marcar como paga."
            else:
                total = sum((o2.valor_real or c2.valor_estimado or 0) for o2, c2 in vencendo)
                titulo, corpo = f"{len(vencendo)} contas vencem nos próximos dias", f"{_moeda(total)} no total. {c.nome} vence {quando}."
            resumo["enviados"] += enviar_para_usuario(u.id, titulo, corpo, "/contas", "vencimento")
        if atrasadas:
            total = sum((o2.valor_real or c2.valor_estimado or 0) for o2, c2 in atrasadas)
            nomes = ", ".join(c2.nome for _, c2 in atrasadas[:2])
            plural = "s" if len(atrasadas) > 1 else ""
            resumo["enviados"] += enviar_para_usuario(u.id, f"{len(atrasadas)} conta{plural} atrasada{plural}", f"{nomes} — {_moeda(total)}.", "/contas", "atraso")
    db.session.commit()
    return resumo
