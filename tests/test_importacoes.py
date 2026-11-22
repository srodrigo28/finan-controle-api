"""Importação por IA. Nenhum teste chama a Anthropic: `ler_documento` é trocado por um falso."""
import io
import os
from datetime import date

import pytest

from app.servicos import leitor_ia
from app.servicos.leitor_ia import ErroLeitura, Leitura, LinhaLida, ResultadoLeitura
from tests.conftest import registrar

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _arquivo(conteudo: bytes = PNG, nome: str = "cupom.png", mime: str = "image/png"):
    return {"arquivo": (io.BytesIO(conteudo), nome, mime)}


def _enviar(api, **kw):
    return api.c.post("/api/v1/importacoes", data=_arquivo(**kw), headers=api.cabecalhos, content_type="multipart/form-data")


@pytest.fixture(autouse=True)
def leitor(monkeypatch):
    """Leitor falso: devolve as linhas configuradas e guarda o que recebeu."""
    estado = {"linhas": [], "erro": None, "chamadas": []}

    def falso(conteudo, mime, categorias, hoje):
        estado["chamadas"].append({"mime": mime, "categorias": categorias, "hoje": hoje, "tamanho": len(conteudo), "conteudo": conteudo})
        if estado["erro"]:
            raise ErroLeitura(estado["erro"])
        return Leitura(
            resultado=ResultadoLeitura(tipo_documento="cupom", estabelecimento="Mercado Bom Preço", linhas=estado["linhas"], observacao=None, conta=None),
            modelo="claude-sonnet-5-5", tokens_entrada=3000, tokens_saida=200,
        )

    monkeypatch.setattr(leitor_ia, "ler_documento", falso)
    return estado


def _linha(**kw) -> LinhaLida:
    base = dict(data="2026-11-18", valor_centavos=7362, tipo="despesa", descricao="Mercado Bom Preço",
                categoria_id=None, forma_pagamento="debito", confianca="alta")
    base.update(kw)
    return LinhaLida(**base)


def test_cupom_vira_rascunho_e_original_fica_guardado(api, leitor, app):
    mercado = api.categoria("Mercado")
    leitor["linhas"] = [_linha(categoria_id=mercado["id"])]
    r = _enviar(api)
    assert r.status_code == 202, r.get_json()
    imp = r.get_json()
    assert imp["estado"] == "revisar"
    assert imp["linhas"] == [{
        "data": "2026-11-18", "valor": 73.62, "tipo": "despesa", "descricao": "Mercado Bom Preço",
        "categoria_id": mercado["id"], "forma_pagamento": "debito", "confianca": "alta", "incluir": True,
        "destino": "lancamento", "conta": None, "parece_lancado": None,
    }]
    assert imp["duplicada_de"] is None
    # a IA recebeu as categorias do usuário
    assert {"id": mercado["id"], "nome": "Mercado"} in leitor["chamadas"][0]["categorias"]
    # o original está no disco, servido pela API
    arq = api.get(f"/importacoes/{imp['id']}/arquivo")
    assert arq.status_code == 200 and arq.data == PNG
    assert any(os.scandir(os.path.join(app.config["UPLOAD_DIR"], "importacoes")))


def test_confirmar_cria_lancamentos_marcados_e_e_idempotente(api, leitor):
    leitor["linhas"] = [_linha(), _linha(valor_centavos=1000, descricao="Estorno", tipo="receita")]
    imp = _enviar(api).get_json()
    linhas = imp["linhas"]
    linhas[1]["incluir"] = False
    linhas[0]["descricao"] = "Mercado do bairro"
    assert api.patch(f"/importacoes/{imp['id']}", {"linhas": linhas}).status_code == 200

    r = api.post(f"/importacoes/{imp['id']}/confirmar")
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert corpo["importacao"]["estado"] == "concluida"
    assert len(corpo["lancamentos"]) == 1
    lanc = corpo["lancamentos"][0]
    assert (lanc["descricao"], lanc["valor"], lanc["data"], lanc["importacao_id"]) == ("Mercado do bairro", 73.62, "2026-11-18", imp["id"])

    de_novo = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()
    assert [l["id"] for l in de_novo["lancamentos"]] == [lanc["id"]]
    assert api.get("/lancamentos").get_json()["total"] == 1


def test_linha_sem_data_nao_confirma(api, leitor):
    leitor["linhas"] = [_linha(data=None)]
    imp = _enviar(api).get_json()
    assert imp["linhas"][0]["confianca"] == "baixa"
    r = api.post(f"/importacoes/{imp['id']}/confirmar")
    assert r.status_code == 422 and r.get_json()["erro"]["detalhes"]["linhas"] == [0]


def test_categoria_fora_da_lista_vira_nula(api, leitor):
    leitor["linhas"] = [_linha(categoria_id="00000000-0000-0000-0000-000000000000")]
    assert _enviar(api).get_json()["linhas"][0]["categoria_id"] is None


def test_erro_da_ia_vira_estado_erro_e_reler_funciona(api, leitor):
    leitor["erro"] = "A IA não aceitou ler este documento."
    imp = _enviar(api).get_json()
    assert (imp["estado"], imp["erro"]) == ("erro", "A IA não aceitou ler este documento.")
    leitor["erro"] = None
    leitor["linhas"] = [_linha()]
    r = api.post(f"/importacoes/{imp['id']}/reler")
    assert r.status_code == 202 and r.get_json()["estado"] == "revisar"
    assert r.get_json()["tentativas"] == 2
    # em revisão não se relê (cada leitura custa)
    assert api.post(f"/importacoes/{imp['id']}/reler").status_code == 409


def test_reler_tem_teto_de_tres_leituras(api, leitor):
    leitor["erro"] = "ilegível"
    imp = _enviar(api).get_json()
    assert api.post(f"/importacoes/{imp['id']}/reler").status_code == 202
    assert api.post(f"/importacoes/{imp['id']}/reler").status_code == 202
    r = api.post(f"/importacoes/{imp['id']}/reler")
    assert r.status_code == 429 and r.get_json()["erro"]["codigo"] == "LIMITE_TENTATIVAS"
    assert len(leitor["chamadas"]) == 3


def test_mesmo_arquivo_e_recusado_salvo_forcar(api, leitor):
    primeira = _enviar(api).get_json()
    r = _enviar(api)
    assert r.status_code == 409 and r.get_json()["erro"]["detalhes"]["importacao_id"] == primeira["id"]
    assert len(leitor["chamadas"]) == 1  # a segunda não chamou a IA
    forcada = api.c.post("/api/v1/importacoes?forcar=1", data=_arquivo(), headers=api.cabecalhos, content_type="multipart/form-data")
    assert forcada.status_code == 202 and forcada.get_json()["duplicada_de"]["id"] == primeira["id"]


def test_conteudo_que_nao_bate_com_o_tipo(api, leitor):
    r = _enviar(api, conteudo=b"%PDF-1.4 falso", nome="foto.png", mime="image/png")
    assert r.status_code == 422


def test_confirmar_aplica_as_linhas_enviadas(api, leitor):
    leitor["linhas"] = [_linha(data=None)]
    imp = _enviar(api).get_json()
    linhas = imp["linhas"]
    linhas[0].update(data="2026-11-20", incluir=True)
    r = api.post(f"/importacoes/{imp['id']}/confirmar", {"linhas": linhas})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["lancamentos"][0]["data"] == "2026-11-20"


def test_leitura_presa_vira_erro(api, leitor, app):
    from datetime import datetime, timedelta, timezone

    from app.extensoes import db
    from app.modelos import Importacao

    imp = _enviar(api).get_json()
    registro = db.session.get(Importacao, __import__("uuid").UUID(imp["id"]))
    registro.estado = "lendo"
    db.session.commit()
    db.session.execute(
        db.text("UPDATE importacao SET atualizado_em = :t WHERE id = :i"),
        {"t": datetime.now(timezone.utc) - timedelta(hours=1), "i": registro.id},
    )
    db.session.commit()
    assert api.get(f"/importacoes/{imp['id']}").get_json()["estado"] == "erro"


def test_confirmar_anexa_o_original_a_cada_lancamento(api, leitor):
    """O original vira anexo de cada lançamento criado, sem cópia: o mesmo arquivo da importação."""
    leitor["linhas"] = [_linha(), _linha(valor_centavos=1500, descricao="Padaria")]
    imp = _enviar(api).get_json()
    lancs = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()["lancamentos"]
    assert len(lancs) == 2
    for lanc in lancs:
        assert len(lanc["anexos"]) == 1
        anexo = lanc["anexos"][0]
        assert (anexo["armazenamento"], anexo["nome"], anexo["tipo_mime"], anexo["importacao_id"]) == (
            "importacao", "cupom.png", "image/png", imp["id"],
        )
        arq = api.get(f"/anexos/{anexo['id']}/arquivo")
        assert arq.status_code == 200 and arq.data == PNG
        assert "no-store" in arq.headers["Cache-Control"]
    # confirmar de novo não duplica o anexo
    de_novo = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()["lancamentos"]
    assert all(len(l["anexos"]) == 1 for l in de_novo)


def test_excluir_anexo_ou_lancamento_nao_apaga_o_original(api, leitor):
    leitor["linhas"] = [_linha(), _linha(valor_centavos=1500, descricao="Padaria")]
    imp = _enviar(api).get_json()
    lancs = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()["lancamentos"]

    assert api.delete(f"/anexos/{lancs[0]['anexos'][0]['id']}").status_code == 204
    assert api.get(f"/importacoes/{imp['id']}/arquivo").data == PNG
    assert api.delete(f"/lancamentos/{lancs[1]['id']}").status_code == 204
    assert api.get(f"/importacoes/{imp['id']}/arquivo").data == PNG


def test_anexo_da_importacao_de_outro_usuario_da_404(api, outro_api, leitor):
    leitor["linhas"] = [_linha()]
    imp = _enviar(api).get_json()
    anexo = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()["lancamentos"][0]["anexos"][0]
    assert outro_api.get(f"/anexos/{anexo['id']}/arquivo").status_code == 404
    assert outro_api.delete(f"/anexos/{anexo['id']}").status_code == 404


def test_exportacao_json_leva_importacao_id(api, leitor):
    leitor["linhas"] = [_linha()]
    imp = _enviar(api).get_json()
    api.post(f"/importacoes/{imp['id']}/confirmar")
    corpo = api.get("/exportar/lancamentos.json").get_json()
    lancs = corpo["dados"] if isinstance(corpo, dict) and "dados" in corpo else corpo.get("lancamentos", corpo)
    assert any(l.get("importacao_id") == imp["id"] for l in lancs)


def test_foto_grande_e_reduzida_so_para_a_leitura():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4000, 1000), "white").save(buf, format="PNG")
    original = buf.getvalue()
    reduzida, mime = leitor_ia.preparar_imagem(original, "image/png")
    assert mime == "image/jpeg"
    assert max(Image.open(io.BytesIO(reduzida)).size) == 2048
    pequena, mime2 = leitor_ia.preparar_imagem(_png_pequeno(), "image/png")
    assert mime2 == "image/png"


def _png_pequeno() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_outro_usuario_nao_ve_nem_baixa(api, outro_api, leitor):
    imp = _enviar(api).get_json()
    assert outro_api.get(f"/importacoes/{imp['id']}").status_code == 404
    assert outro_api.get(f"/importacoes/{imp['id']}/arquivo").status_code == 404
    assert outro_api.post(f"/importacoes/{imp['id']}/confirmar").status_code == 404
    assert outro_api.get("/importacoes").get_json()["dados"] == []


def test_tipo_de_arquivo_invalido(api, leitor):
    r = _enviar(api, conteudo=b"ola", nome="x.txt", mime="text/plain")
    assert r.status_code == 422


def test_sem_chave_responde_503(api, leitor, app, monkeypatch):
    monkeypatch.setitem(app.config, "ANTHROPIC_API_KEY", "")
    r = _enviar(api)
    assert r.status_code == 503 and r.get_json()["erro"]["codigo"] == "IA_INDISPONIVEL"


def test_limite_do_mes(api, leitor, app, monkeypatch):
    monkeypatch.setitem(app.config, "IMPORTACAO_LIMITE_MES", 1)
    assert _enviar(api).status_code == 202
    r = _enviar(api, conteudo=PNG + b"1")  # outro arquivo: o duplicado daria 409 antes do limite
    assert r.status_code == 429 and r.get_json()["erro"]["codigo"] == "LIMITE_IMPORTACAO"


def test_descartar_guarda_original_e_bloqueia_confirmar(api, leitor):
    leitor["linhas"] = [_linha()]
    imp = _enviar(api).get_json()
    assert api.post(f"/importacoes/{imp['id']}/descartar").get_json()["estado"] == "descartada"
    assert api.get(f"/importacoes/{imp['id']}/arquivo").status_code == 200
    assert api.post(f"/importacoes/{imp['id']}/confirmar").status_code == 409


def test_data_de_referencia_e_o_dia_de_sao_paulo(api, leitor, monkeypatch):
    from app.servicos import importacoes
    monkeypatch.setattr(importacoes, "hoje", lambda: date(2026, 1, 1))
    leitor["linhas"] = [_linha()]
    _enviar(api)
    assert leitor["chamadas"][0]["hoje"] == date(2026, 1, 1)


# ---------- PDF com senha (F6b) ----------

def _pdf(senha_usuario: str | None = None, senha_dono: str | None = None) -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    if senha_usuario is not None:
        w.encrypt(user_password=senha_usuario, owner_password=senha_dono or "dono-123", algorithm="AES-256")
    saida = io.BytesIO()
    w.write(saida)
    return saida.getvalue()


def _protegido(conteudo: bytes) -> bool:
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(conteudo)).is_encrypted


def _enviar_pdf(api, conteudo: bytes):
    return _enviar(api, conteudo=conteudo, nome="extrato.pdf", mime="application/pdf")


def test_pdf_com_senha_espera_a_senha_sem_chamar_a_ia(api, leitor):
    pdf = _pdf("12345")
    r = _enviar_pdf(api, pdf)
    assert r.status_code == 202, r.get_json()
    imp = r.get_json()
    assert imp["estado"] == "senha" and imp["tentativas"] == 0
    assert leitor["chamadas"] == []
    # o original guardado é o arquivo protegido, intacto
    assert api.get(f"/importacoes/{imp['id']}/arquivo").data == pdf


def test_senha_errada_da_422_e_nao_gasta_leitura(api, leitor):
    imp = _enviar_pdf(api, _pdf("12345")).get_json()
    r = api.post(f"/importacoes/{imp['id']}/senha", {"senha": "99999"})
    assert r.status_code == 422 and r.get_json()["erro"]["codigo"] == "SENHA_INCORRETA", r.get_json()
    detalhe = api.get(f"/importacoes/{imp['id']}").get_json()
    assert (detalhe["estado"], detalhe["tentativas"]) == ("senha", 0)
    assert leitor["chamadas"] == []


def test_senha_certa_le_a_copia_aberta_e_nao_grava_a_senha(api, leitor, app):
    from app.extensoes import db

    leitor["linhas"] = [_linha()]
    pdf = _pdf("12345")
    imp = _enviar_pdf(api, pdf).get_json()
    r = api.post(f"/importacoes/{imp['id']}/senha", {"senha": "12345"})
    assert r.status_code == 202, r.get_json()
    assert api.get(f"/importacoes/{imp['id']}").get_json()["estado"] == "revisar"
    # a IA recebeu um PDF sem senha; o original continua protegido
    assert len(leitor["chamadas"]) == 1 and not _protegido(leitor["chamadas"][0]["conteudo"])
    assert api.get(f"/importacoes/{imp['id']}/arquivo").data == pdf
    with app.app_context():
        linha = db.session.execute(db.text("SELECT row_to_json(i)::text FROM importacao i WHERE id = :i"), {"i": imp["id"]}).scalar()
    assert "12345" not in linha


def test_pdf_so_com_senha_de_dono_le_direto(api, leitor):
    """Senha de abertura vazia (só restrição de impressão/cópia): o usuário não precisa digitar nada."""
    leitor["linhas"] = [_linha()]
    imp = _enviar_pdf(api, _pdf("")).get_json()
    assert imp["estado"] == "revisar"
    assert not _protegido(leitor["chamadas"][0]["conteudo"])


def test_reler_pdf_com_senha_pede_a_senha_de_novo(api, leitor):
    leitor["erro"] = "A leitura por IA falhou. Tente de novo."
    imp = _enviar_pdf(api, _pdf("12345")).get_json()
    assert api.post(f"/importacoes/{imp['id']}/senha", {"senha": "12345"}).status_code == 202
    assert api.get(f"/importacoes/{imp['id']}").get_json()["estado"] == "erro"
    leitor["erro"] = None
    r = api.post(f"/importacoes/{imp['id']}/reler")
    assert r.status_code == 202 and r.get_json()["estado"] == "senha"
    assert len(leitor["chamadas"]) == 1


def test_senha_fora_do_estado_ou_vazia(api, leitor):
    leitor["linhas"] = [_linha()]
    imp = _enviar(api).get_json()  # PNG, já em revisão
    assert api.post(f"/importacoes/{imp['id']}/senha", {"senha": "1"}).status_code == 409
    protegido = _enviar_pdf(api, _pdf("12345")).get_json()
    assert api.post(f"/importacoes/{protegido['id']}/senha", {"senha": ""}).status_code == 422
