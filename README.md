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

## E-mail (confirmação de cadastro e senha)

Padrão 99dev — desenho e motivos em `../docs/prompts/6-setembro-validacao-smtp-esqueci-senha.md`.

`MAIL_HOST` vazio (padrão em dev) faz a API **só logar** o e-mail, com o link no log — dá para seguir o fluxo
inteiro sem SMTP. `EMAIL_VERIFICATION_TEST_CODE=1234` confirma qualquer conta (é o que o e2e do front usa);
em produção fica **vazio**.

Antes de culpar o código quando o e-mail "não chega", rode o diagnóstico — ele responde se o e-mail
consegue *sair*, sem depender de caixa de entrada:

```bash
python scripts/checar_smtp.py                          # config -> porta 587 -> login
python scripts/checar_smtp.py --enviar voce@gmail.com  # envia um de verdade
docker exec -it finan-api python scripts/checar_smtp.py   # na VPS: o .env de lá é outro
```

Senha de app do Gmail tem 16 caracteres e **os espaços que o Google mostra não entram no `.env`**; ela é
revogada em silêncio, e `535 5.7.8` no login é exatamente isso.

## Estrutura

```
app/
  __init__.py     fábrica create_app + handlers de erro/JWT
  config.py       configuração por variáveis de ambiente
  extensoes.py    db, migrate, jwt, cors
  modelos/        ORM (SQLAlchemy 2, IDs UUID)
  esquemas/       validação de entrada (pydantic v2)
  rotas/          blueprints (auth, categorias, lancamentos, sessoes, precos, contas, metricas, exportar, saude)
  servicos/       regras de negócio (fechar sessão, sincronização offline, ocorrências, métricas,
                  e-mail/SMTP, confirmação de cadastro, redefinição de senha)
scripts/          checar_smtp.py (diagnóstico do canal de e-mail)
migrations/       Alembic
tests/            pytest
```
