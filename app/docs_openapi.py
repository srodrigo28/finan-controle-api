"""Especificação OpenAPI 3.1 da API, montada a partir dos esquemas pydantic e do contrato (docs/API.md)."""
from typing import Any

from app.esquemas import auth, categoria, conta, lancamento, sessao

REF = "#/components/schemas/{model}"

# Esquemas de ENTRADA (pydantic) → components.schemas
ENTRADAS = [
    auth.Registrar, auth.Login, auth.AtualizarEu,
    categoria.CriarCategoria, categoria.AtualizarCategoria, categoria.Reordenar,
    lancamento.CriarLancamento, lancamento.AtualizarLancamento,
    sessao.CriarSessao, sessao.AtualizarSessao, sessao.CriarItem, sessao.AtualizarItem,
    sessao.FecharSessao, sessao.Sincronizar,
    conta.CriarConta, conta.AtualizarConta, conta.PagarOcorrencia,
]

# Esquemas de SAÍDA (descritos à mão, espelhando docs/API.md)
UUID = {"type": "string", "format": "uuid"}
DATA = {"type": "string", "format": "date", "example": "2026-08-30"}
TS = {"type": "string", "format": "date-time"}
VALOR = {"type": "number", "format": "double", "example": 12.5}

SAIDAS: dict[str, dict[str, Any]] = {
    "Erro": {
        "type": "object",
        "properties": {"erro": {"type": "object", "properties": {
            "codigo": {"type": "string", "example": "VALIDACAO"},
            "mensagem": {"type": "string"},
            "detalhes": {"type": "object", "additionalProperties": True},
        }}},
    },
    "Usuario": {"type": "object", "properties": {
        "id": UUID, "nome": {"type": "string"}, "email": {"type": "string", "format": "email"},
        "moeda": {"type": "string", "example": "BRL"}, "orcamento_mensal": {**VALOR, "nullable": True},
        "orcamento_diario": {**VALOR, "nullable": True},
        "plano": {"type": "string", "enum": ["teste", "completo"]}, "teste_expira_em": {**TS, "nullable": True},
        "dias_restantes_teste": {"type": "integer", "nullable": True}, "teste_ativo": {"type": "boolean"}, "criado_em": TS}},
    "Tokens": {"type": "object", "properties": {
        "usuario": {"$ref": REF.format(model="Usuario")},
        "access_token": {"type": "string"}, "refresh_token": {"type": "string"}}},
    "Categoria": {"type": "object", "properties": {
        "id": UUID, "nome": {"type": "string"}, "cor": {"type": "string", "example": "#10B981"},
        "icone": {"type": "string", "example": "shopping-cart"}, "pai_id": {**UUID, "nullable": True},
        "orcamento_mensal": {**VALOR, "nullable": True}, "arquivada": {"type": "boolean"},
        "ordem": {"type": "integer"}, "criado_em": TS}},
    "Anexo": {"type": "object", "properties": {
        "id": UUID, "lancamento_id": UUID, "nome": {"type": "string"}, "tipo_mime": {"type": "string"},
        "tamanho": {"type": "integer"}, "url": {"type": "string"}, "criado_em": TS}},
    "Item": {"type": "object", "properties": {
        "id": UUID, "sessao_id": UUID, "descricao": {"type": "string"}, "categoria_id": {**UUID, "nullable": True},
        "valor_unitario": VALOR, "quantidade": {"type": "number", "example": 1.5}, "subtotal": VALOR,
        "removido": {"type": "boolean"}, "criado_em": TS, "atualizado_em": TS}},
    "Lancamento": {"type": "object", "properties": {
        "id": UUID, "tipo": {"type": "string", "enum": ["despesa", "receita"]}, "valor": VALOR,
        "categoria_id": {**UUID, "nullable": True}, "descricao": {"type": "string"}, "data": DATA,
        "forma_pagamento": {"type": "string", "nullable": True, "enum": ["dinheiro", "debito", "credito", "pix", "boleto", "outro"]},
        "sessao_id": {**UUID, "nullable": True}, "conta_id": {**UUID, "nullable": True},
        "anexos": {"type": "array", "items": {"$ref": REF.format(model="Anexo")}},
        "itens": {"type": "array", "items": {"$ref": REF.format(model="Item")}},
        "criado_em": TS, "atualizado_em": TS}},
    "Sessao": {"type": "object", "properties": {
        "id": UUID, "local": {"type": "string", "nullable": True}, "orcamento": {**VALOR, "nullable": True},
        "status": {"type": "string", "enum": ["aberta", "fechada", "abandonada"]}, "aberta_em": TS,
        "fechada_em": {**TS, "nullable": True}, "total_carrinho": VALOR, "total_pago": {**VALOR, "nullable": True},
        "motivo_divergencia": {"type": "string", "nullable": True}, "lancamento_id": {**UUID, "nullable": True},
        "atualizado_em": TS, "itens": {"type": "array", "items": {"$ref": REF.format(model="Item")}}}},
    "Conta": {"type": "object", "properties": {
        "id": UUID, "nome": {"type": "string"}, "valor_estimado": VALOR, "dia_vencimento": {"type": "integer"},
        "recorrencia": {"type": "string", "enum": ["mensal", "semanal", "anual", "unica"]},
        "categoria_id": {**UUID, "nullable": True}, "ativa": {"type": "boolean"}, "lembrete_dias": {"type": "integer"},
        "criado_em": TS}},
    "Ocorrencia": {"type": "object", "properties": {
        "id": UUID, "conta_id": UUID, "competencia": {"type": "string", "example": "2026-08"}, "vencimento": DATA,
        "valor_real": {**VALOR, "nullable": True}, "status": {"type": "string", "enum": ["pendente", "paga", "atrasada"]},
        "lancamento_id": {**UUID, "nullable": True},
        "conta": {"type": "object", "properties": {"nome": {"type": "string"}, "categoria_id": {**UUID, "nullable": True}, "valor_estimado": VALOR}}}},
    "MetricaDiaria": {"type": "object", "properties": {
        "data": DATA, "total_despesas": VALOR, "total_receitas": VALOR, "orcamento_diario": {**VALOR, "nullable": True},
        "saldo_orcamento": {**VALOR, "nullable": True},
        "por_categoria": {"type": "array", "items": {"type": "object", "properties": {"categoria_id": {**UUID, "nullable": True}, "total": VALOR}}},
        "lancamentos": {"type": "array", "items": {"$ref": REF.format(model="Lancamento")}}}},
    "MetricaSemanal": {"type": "object", "properties": {
        "inicio": DATA, "fim": DATA, "total": VALOR, "total_anterior": VALOR, "variacao_valor": VALOR,
        "variacao_pct": {"type": "number", "nullable": True},
        "por_dia": {"type": "array", "items": {"type": "object", "properties": {"data": DATA, "total": VALOR}}},
        "por_categoria": {"type": "array", "items": {"type": "object", "properties": {"categoria_id": {**UUID, "nullable": True}, "total": VALOR, "pct": {"type": "number"}}}},
        "dia_mais_caro": {**DATA, "nullable": True}, "semana_mais_cara_do_mes": {"type": "boolean"}}},
    "MetricaMensal": {"type": "object", "properties": {
        "mes": {"type": "string", "example": "2026-08"}, "total_despesas": VALOR, "total_receitas": VALOR, "saldo": VALOR,
        "orcamento_mensal": {**VALOR, "nullable": True},
        "meses_anteriores": {"type": "array", "items": {"type": "object", "properties": {"mes": {"type": "string"}, "total": VALOR}}},
        "por_categoria": {"type": "array", "items": {"type": "object", "properties": {"categoria_id": {**UUID, "nullable": True}, "total": VALOR, "orcamento": {**VALOR, "nullable": True}, "pct_orcamento": {"type": "number", "nullable": True}}}},
        "contas": {"type": "object", "properties": {"pagas": {"type": "integer"}, "pendentes": {"type": "integer"}, "total_pendente": VALOR}},
        "projecao_fechamento": VALOR,
        "semanas": {"type": "array", "items": {"type": "object", "properties": {"inicio": DATA, "fim": DATA, "total": VALOR}}}}},
    "Saude": {"type": "object", "properties": {"status": {"type": "string", "example": "ok"}, "banco": {"type": "string", "example": "ok"}}},
}


def _ref(nome: str) -> dict:
    return {"$ref": REF.format(model=nome)}


def _lista(nome: str) -> dict:
    return {"type": "object", "properties": {"dados": {"type": "array", "items": _ref(nome)}}}


def _paginado(nome: str) -> dict:
    return {"type": "object", "properties": {
        "dados": {"type": "array", "items": _ref(nome)}, "total": {"type": "integer"},
        "pagina": {"type": "integer"}, "por_pagina": {"type": "integer"}}}


def _resp(schema: dict | None, descricao: str = "OK", status: str = "200") -> dict:
    conteudo = {"content": {"application/json": {"schema": schema}}} if schema else {}
    return {status: {"description": descricao, **conteudo}}


ERROS = {
    "400": {"description": "Requisição inválida", "content": {"application/json": {"schema": _ref("Erro")}}},
    "401": {"description": "Não autenticado", "content": {"application/json": {"schema": _ref("Erro")}}},
    "404": {"description": "Não encontrado", "content": {"application/json": {"schema": _ref("Erro")}}},
    "422": {"description": "Erro de validação", "content": {"application/json": {"schema": _ref("Erro")}}},
}


def _corpo(modelo: type) -> dict:
    return {"required": True, "content": {"application/json": {"schema": _ref(modelo.__name__)}}}


def _param(nome: str, onde: str = "query", tipo: str = "string", obrigatorio: bool = False, descricao: str = "", **extra) -> dict:
    p = {"name": nome, "in": onde, "required": obrigatorio or onde == "path", "schema": {"type": tipo, **extra}}
    if descricao:
        p["description"] = descricao
    return p


P_ID = _param("id", "path", "string", format="uuid")


def _op(tag: str, resumo: str, respostas: dict, corpo: dict | None = None, params: list | None = None,
        publico: bool = False, descricao: str = "") -> dict:
    op: dict[str, Any] = {"tags": [tag], "summary": resumo, "responses": {**respostas, **ERROS}}
    if descricao:
        op["description"] = descricao
    if corpo:
        op["requestBody"] = corpo
    if params:
        op["parameters"] = params
    if publico:
        op["security"] = []
    return op


def montar_spec(servidor: str) -> dict[str, Any]:
    """Monta o documento OpenAPI. `servidor` = prefixo público (ex.: "/finan-controle-api" ou "/")."""
    componentes: dict[str, Any] = {}
    for modelo in ENTRADAS:
        schema = modelo.model_json_schema(ref_template=REF)
        for nome, definicao in (schema.pop("$defs", {}) or {}).items():
            componentes.setdefault(nome, definicao)
        componentes[modelo.__name__] = schema
    componentes.update(SAIDAS)

    v1 = "/api/v1"
    paths: dict[str, Any] = {
        "/healthz": {"get": _op("Infra", "Saúde da API e do banco", _resp(_ref("Saude")), publico=True)},

        f"{v1}/auth/registrar": {"post": _op("Auth", "Criar conta (gera categorias padrão)", _resp(_ref("Tokens"), "Criado", "201"), _corpo(auth.Registrar), publico=True)},
        f"{v1}/auth/login": {"post": _op("Auth", "Entrar", _resp(_ref("Tokens")), _corpo(auth.Login), publico=True)},
        f"{v1}/auth/refresh": {"post": _op("Auth", "Renovar access token (Bearer = refresh_token)", _resp({"type": "object", "properties": {"access_token": {"type": "string"}}}))},
        f"{v1}/auth/eu": {
            "get": _op("Auth", "Usuário autenticado", _resp(_ref("Usuario"))),
            "patch": _op("Auth", "Atualizar nome e orçamentos", _resp(_ref("Usuario")), _corpo(auth.AtualizarEu)),
        },

        f"{v1}/categorias": {
            "get": _op("Categorias", "Listar", _resp(_lista("Categoria")), params=[_param("incluir_arquivadas", tipo="integer", enum=[0, 1])]),
            "post": _op("Categorias", "Criar (aceita id do cliente)", _resp(_ref("Categoria"), "Criada", "201"), _corpo(categoria.CriarCategoria)),
        },
        f"{v1}/categorias/{{id}}": {
            "patch": _op("Categorias", "Atualizar (inclusive arquivada)", _resp(_ref("Categoria")), _corpo(categoria.AtualizarCategoria), [P_ID]),
            "delete": _op("Categorias", "Arquivar (nunca apaga)", _resp(None, "Arquivada", "204"), params=[P_ID]),
        },
        f"{v1}/categorias/reordenar": {"post": _op("Categorias", "Reordenar", _resp(None, "OK", "204"), _corpo(categoria.Reordenar))},

        f"{v1}/lancamentos": {
            "get": _op("Lançamentos", "Listar (paginado, data desc)", _resp(_paginado("Lancamento")), params=[
                _param("de", format="date"), _param("ate", format="date"), _param("tipo", enum=["despesa", "receita"]),
                _param("categoria_id", format="uuid"), _param("busca"), _param("pagina", tipo="integer", default=1),
                _param("por_pagina", tipo="integer", default=50)]),
            "post": _op("Lançamentos", "Criar despesa/receita", _resp(_ref("Lancamento"), "Criado", "201"), _corpo(lancamento.CriarLancamento)),
        },
        f"{v1}/lancamentos/{{id}}": {
            "get": _op("Lançamentos", "Detalhe (com itens se veio do Modo Mercado)", _resp(_ref("Lancamento")), params=[P_ID]),
            "patch": _op("Lançamentos", "Atualizar", _resp(_ref("Lancamento")), _corpo(lancamento.AtualizarLancamento), [P_ID]),
            "delete": _op("Lançamentos", "Excluir", _resp(None, "Excluído", "204"), params=[P_ID]),
        },
        f"{v1}/lancamentos/{{id}}/anexos": {"post": _op("Lançamentos", "Anexar comprovante (jpg/png/webp/pdf ≤ 8MB)", _resp(_ref("Anexo"), "Criado", "201"),
            {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "properties": {"arquivo": {"type": "string", "format": "binary"}}}}}}, [P_ID])},
        f"{v1}/anexos/{{id}}": {"delete": _op("Lançamentos", "Remover anexo", _resp(None, "Removido", "204"), params=[P_ID])},
        f"{v1}/anexos/{{id}}/arquivo": {"get": _op("Lançamentos", "Baixar anexo (autenticado)", {"200": {"description": "Binário", "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}}, params=[P_ID])},

        f"{v1}/sessoes": {
            "get": _op("Modo Mercado", "Listar sessões (sem itens)", _resp(_lista("Sessao")), params=[_param("status", enum=["aberta", "fechada", "abandonada"])]),
            "post": _op("Modo Mercado", "Abrir sessão de compra", _resp(_ref("Sessao"), "Criada", "201"), _corpo(sessao.CriarSessao)),
        },
        f"{v1}/sessoes/sincronizar": {"post": _op("Modo Mercado", "Sincronizar sessões offline (upsert idempotente por id)", _resp({"type": "object", "properties": {"sessoes": {"type": "array", "items": _ref("Sessao")}}}), _corpo(sessao.Sincronizar),
            descricao="O cliente manda o estado inteiro (sessão + itens). Regra: último `atualizado_em` vence por item. Sessão `fechada` sem `lancamento_id` executa o fechamento (gera 1 lançamento e histórico de preço).")},
        f"{v1}/sessoes/{{id}}": {
            "get": _op("Modo Mercado", "Sessão com itens", _resp(_ref("Sessao")), params=[P_ID]),
            "patch": _op("Modo Mercado", "Atualizar local/orçamento", _resp(_ref("Sessao")), _corpo(sessao.AtualizarSessao), [P_ID]),
        },
        f"{v1}/sessoes/{{id}}/itens": {"post": _op("Modo Mercado", "Adicionar item", _resp(_ref("Item"), "Criado", "201"), _corpo(sessao.CriarItem), [P_ID])},
        f"{v1}/sessoes/{{id}}/itens/{{item_id}}": {
            "patch": _op("Modo Mercado", "Editar item", _resp(_ref("Item")), _corpo(sessao.AtualizarItem), [P_ID, _param("item_id", "path", format="uuid")]),
            "delete": _op("Modo Mercado", "Remover item (marca removido)", _resp(None, "Removido", "204"), params=[P_ID, _param("item_id", "path", format="uuid")]),
        },
        f"{v1}/sessoes/{{id}}/fechar": {"post": _op("Modo Mercado", "Fechar no caixa → gera lançamento", _resp({"type": "object", "properties": {"sessao": _ref("Sessao"), "lancamento": _ref("Lancamento")}}), _corpo(sessao.FecharSessao), [P_ID])},
        f"{v1}/sessoes/{{id}}/abandonar": {"post": _op("Modo Mercado", "Abandonar sessão", _resp(None, "OK", "204"), params=[P_ID])},

        f"{v1}/precos/ultimo": {"get": _op("Preços", "Último preço pago por descrição", _resp({"type": "object", "nullable": True, "properties": {"descricao_normalizada": {"type": "string"}, "valor_unitario": VALOR, "data": DATA, "sessao_id": UUID}}), params=[_param("descricao", obrigatorio=True)])},
        f"{v1}/precos/sugestoes": {"get": _op("Preços", "Autocomplete a partir do histórico", _resp({"type": "object", "properties": {"dados": {"type": "array", "items": {"type": "object", "properties": {"descricao": {"type": "string"}, "categoria_id": {**UUID, "nullable": True}, "valor_unitario": VALOR}}}}}), params=[_param("q", obrigatorio=True)])},

        f"{v1}/contas": {
            "get": _op("Contas", "Listar contas agendadas", _resp(_lista("Conta")), params=[_param("incluir_inativas", tipo="integer", enum=[0, 1])]),
            "post": _op("Contas", "Criar conta agendada", _resp(_ref("Conta"), "Criada", "201"), _corpo(conta.CriarConta)),
        },
        f"{v1}/contas/{{id}}": {
            "patch": _op("Contas", "Atualizar", _resp(_ref("Conta")), _corpo(conta.AtualizarConta), [P_ID]),
            "delete": _op("Contas", "Desativar", _resp(None, "Desativada", "204"), params=[P_ID]),
        },
        f"{v1}/contas/ocorrencias": {"get": _op("Contas", "Ocorrências da competência (gera as faltantes)", _resp({"type": "object", "properties": {"competencia": {"type": "string"}, "dados": {"type": "array", "items": _ref("Ocorrencia")}, "total_pendente": VALOR, "total_pago": VALOR}}), params=[_param("competencia", obrigatorio=True, example="2026-08")])},
        f"{v1}/contas/ocorrencias/{{id}}/pagar": {"post": _op("Contas", "Pagar → vira lançamento", _resp({"type": "object", "properties": {"ocorrencia": _ref("Ocorrencia"), "lancamento": _ref("Lancamento")}}), _corpo(conta.PagarOcorrencia), [P_ID])},
        f"{v1}/contas/ocorrencias/{{id}}/reabrir": {"post": _op("Contas", "Reabrir ocorrência paga", _resp(_ref("Ocorrencia")), params=[P_ID])},

        f"{v1}/metricas/diario": {"get": _op("Métricas", "Dia: gastos, receitas, saldo do orçamento diário", _resp(_ref("MetricaDiaria")), params=[_param("data", format="date")])},
        f"{v1}/metricas/semanal": {"get": _op("Métricas", "Semana (segunda a domingo) com comparativo", _resp(_ref("MetricaSemanal")), params=[_param("inicio", format="date", descricao="segunda-feira")])},
        f"{v1}/metricas/mensal": {"get": _op("Métricas", "Mês: evolução, categorias, contas, projeção", _resp(_ref("MetricaMensal")), params=[_param("mes", example="2026-08")])},

        f"{v1}/exportar/lancamentos.csv": {"get": _op("Exportação", "CSV (;) com BOM", {"200": {"description": "CSV", "content": {"text/csv": {}}}}, params=[_param("de", format="date"), _param("ate", format="date")])},
        f"{v1}/exportar/lancamentos.json": {"get": _op("Exportação", "JSON completo", {"200": {"description": "JSON", "content": {"application/json": {}}}}, params=[_param("de", format="date"), _param("ate", format="date")])},
    }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Finan — API de controle financeiro",
            "version": "1.0.0",
            "description": (
                "Controle financeiro pessoal com **Modo Mercado** (carrinho offline-first sincronizado por upsert idempotente).\n\n"
                "Convenções: IDs UUID (o cliente pode gerar), valores decimais com 2 casas em BRL, datas `YYYY-MM-DD`, "
                "erros no formato `{\"erro\": {\"codigo\", \"mensagem\", \"detalhes\"}}`. Rotas exigem `Authorization: Bearer <access_token>` "
                "exceto `auth/registrar`, `auth/login` e `/healthz`."
            ),
        },
        "servers": [{"url": servidor}],
        "tags": [{"name": t} for t in ("Infra", "Auth", "Categorias", "Lançamentos", "Modo Mercado", "Preços", "Contas", "Métricas", "Exportação")],
        "components": {
            "schemas": componentes,
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
        },
        "security": [{"bearerAuth": []}],
        "paths": paths,
    }
