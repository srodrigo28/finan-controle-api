"""Insights automáticos: variação por categoria, preço de item, orçamento e semana vazia."""
from datetime import date, timedelta


def _segunda(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _lancar(api, valor, categoria_id, dia, descricao="x"):
    r = api.post("/lancamentos", {"tipo": "despesa", "valor": valor, "categoria_id": categoria_id, "descricao": descricao, "data": dia.isoformat()})
    assert r.status_code == 201, r.get_json()


def test_insights_categoria_subiu_e_orcamento(api):
    mercado = api.categoria("Mercado")
    semana = _segunda(date.today())
    _lancar(api, 100, mercado["id"], semana - timedelta(days=7))  # semana passada
    _lancar(api, 180, mercado["id"], semana)                      # esta semana (+80%)
    api.patch(f"/categorias/{mercado['id']}", {"orcamento_mensal": 200})

    r = api.get("/metricas/insights")
    assert r.status_code == 200, r.get_json()
    dados = r.get_json()["dados"]
    tipos = {i["tipo"] for i in dados}
    assert "categoria_subiu" in tipos
    subiu = next(i for i in dados if i["tipo"] == "categoria_subiu")
    assert "Mercado" in subiu["titulo"] and "80%" in subiu["titulo"] and subiu["nivel"] == "atencao"
    assert tipos & {"orcamento_perto", "orcamento_estourou"}  # 180 (ou 280) de 200
    niveis = [i["nivel"] for i in dados]
    assert niveis == sorted(niveis, key={"atencao": 0, "bom": 1, "info": 2}.get)


def test_insights_preco_de_item(api, app):
    from app.extensoes import db
    from app.modelos import PrecoHistorico

    hoje = date.today()
    for valor, dias in ((24.90, 20), (28.30, 2)):
        s = api.post("/sessoes", {"local": "Mercado"}).get_json()
        api.post(f"/sessoes/{s['id']}/itens", {"descricao": "Arroz 5kg", "valor_unitario": valor, "quantidade": 1})
        r = api.post(f"/sessoes/{s['id']}/fechar", {"total_pago": valor})
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            ph = db.session.query(PrecoHistorico).filter_by(descricao="Arroz 5kg").order_by(PrecoHistorico.criado_em.desc()).first()
            ph.data = hoje - timedelta(days=dias)  # simula compras em dias diferentes
            db.session.commit()

    dados = api.get("/metricas/insights").get_json()["dados"]
    preco = next(i for i in dados if i["tipo"] == "preco_subiu")
    assert "Arroz 5kg" in preco["titulo"] and "3,40" in preco["titulo"]


def test_insights_sem_gastos(api):
    dados = api.get("/metricas/insights").get_json()["dados"]
    assert any(i["tipo"] == "sem_gastos" for i in dados)
