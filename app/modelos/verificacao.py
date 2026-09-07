import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import ModeloBase, uuid_pk

CADASTRO = "cadastro"
SENHA = "senha"


class CodigoVerificacao(ModeloBase):
    """Código/token emitido por e-mail — uma tabela para os dois fluxos.

    `finalidade` separa a confirmação de cadastro (código de 4 dígitos + link) da
    redefinição de senha (só link). Guardar os dois no mesmo lugar mantém uma
    regra única de expiração, uso único e limpeza.

    **Nada é gravado em claro.** `codigo_hash` e `token_hash` são SHA-256: quem lê
    a tabela não confirma conta nem troca a senha de ninguém.
    """

    __tablename__ = "codigo_verificacao"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # O e-mail vigente na emissão. Se a pessoa trocar de e-mail depois, o código
    # antigo deixa de valer — senão o endereço velho ainda confirmaria a conta.
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    finalidade: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    codigo_hash: Mapped[str | None] = mapped_column(String(64))
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    # **É o teto de tentativas que torna 4 dígitos seguro**, não o comprimento:
    # 10.000 combinações caem em minutos se puderem ser varridas à vontade.
    tentativas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
