"""Categorias padrão criadas no registro do usuário."""
import uuid

from app.extensoes import db
from app.modelos import Categoria

PADRAO: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    # (nome, cor, ícone lucide, subcategorias)
    ("Mercado", "#10B981", "shopping-cart", [
        ("Hortifruti", "#34D399", "apple"),
        ("Limpeza", "#6EE7B7", "spray-can"),
        ("Bebidas", "#059669", "cup-soda"),
    ]),
    ("Moradia", "#6366F1", "house", []),
    ("Transporte", "#F59E0B", "car", []),
    ("Alimentação fora", "#F97316", "utensils", []),
    ("Saúde", "#EF4444", "heart-pulse", []),
    ("Lazer", "#EC4899", "party-popper", []),
    ("Educação", "#3B82F6", "graduation-cap", []),
    ("Contas fixas", "#8B5CF6", "receipt", []),
    ("Salário", "#14B8A6", "banknote", []),
    ("Outros", "#6B7280", "tag", []),
]


def criar_categorias_padrao(usuario_id: uuid.UUID) -> list[Categoria]:
    criadas: list[Categoria] = []
    ordem = 0
    for nome, cor, icone, subs in PADRAO:
        pai = Categoria(usuario_id=usuario_id, nome=nome, cor=cor, icone=icone, ordem=ordem)
        db.session.add(pai)
        db.session.flush()
        criadas.append(pai)
        ordem += 1
        for sub_nome, sub_cor, sub_icone in subs:
            sub = Categoria(usuario_id=usuario_id, nome=sub_nome, cor=sub_cor, icone=sub_icone, pai_id=pai.id, ordem=ordem)
            db.session.add(sub)
            criadas.append(sub)
            ordem += 1
    return criadas


def categoria_do_usuario(usuario_id: uuid.UUID, categoria_id: uuid.UUID | None) -> Categoria | None:
    """Garante que a categoria pertence ao usuário; levanta erro se não."""
    if categoria_id is None:
        return None
    cat = db.session.get(Categoria, categoria_id)
    if cat is None or cat.usuario_id != usuario_id:
        from app.erros import ErroApi

        raise ErroApi("VALIDACAO", "Categoria inválida.", 422, {"categoria_id": "não encontrada"})
    return cat
