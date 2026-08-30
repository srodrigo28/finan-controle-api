# finan-controle — API (Flask)

API REST do app de controle financeiro. Contrato completo em `../docs/API.md`.

## Rodar local

```bash
# Postgres do docker-compose da raiz (porta 5434)
docker compose -f ../docker-compose.yml up -d db

python -m venv .venv
.venv/Scripts/activate            # Windows  |  source .venv/bin/activate (Linux/mac)
pip install -r requirements-dev.txt
cp .env.example .env              # já vem apontando para o Postgres local

flask --app run.py db upgrade     # aplica migrações
python run.py                     # http://localhost:8000/healthz
```

## Testes

Os testes usam um Postgres real (`DATABASE_URL_TESTE`, padrão `127.0.0.1:5436`):

```bash
docker run -d --name finan-db-teste -e POSTGRES_PASSWORD=x -e POSTGRES_USER=finan_user -e POSTGRES_DB=finan_controle -p 5436:5432 postgres:16-alpine
pytest
```

## Migrações

```bash
flask --app run.py db migrate -m "descricao"
flask --app run.py db upgrade
```

## Docker

```bash
docker build -t finan-api .
docker run --rm -p 8030:8000 --env-file .env.vps -e RUN_MIGRATIONS_ON_STARTUP=1 finan-api
```

Na VPS a API é publicada em `https://99dev.pro/finan-api/` (nginx envia `X-Forwarded-Prefix`/`X-Script-Name`, tratados por `ProxyFix`).

## Estrutura

```
app/
  __init__.py     fábrica create_app + handlers de erro/JWT
  config.py       configuração por variáveis de ambiente
  extensoes.py    db, migrate, jwt, cors
  modelos/        ORM (SQLAlchemy 2, IDs UUID)
  esquemas/       validação de entrada (pydantic v2)
  rotas/          blueprints (auth, categorias, lancamentos, sessoes, precos, contas, metricas, exportar, saude)
  servicos/       regras de negócio (fechar sessão, sincronização offline, ocorrências, métricas)
migrations/       Alembic
tests/            pytest
```
