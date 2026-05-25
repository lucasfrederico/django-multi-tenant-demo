# django-multi-tenant-demo

Pequeno serviço Django + DRF que recria, em Python, os patterns que rodei
em produção por 5 anos numa plataforma real-time na JVM:

- **Multi-tenancy** com FK por tenant + queryset filter (a mesma estratégia
  de isolamento que usei numa rede com 1.500 usuários simultâneos, sub-50ms
  no hot path)
- **Audit trail** automático via Django signals
- **JWT auth** (djangorestframework-simplejwt)
- **Async tasks** com Celery + Redis (equivalente a RabbitMQ que usei no
  LoverCraft)
- **AuctionItem + Bids** como domínio — porque foi o feature mais hairy do
  meu trabalho real (refatorei 2.800 linhas de JS legacy num serviço Java
  limpo com invariants idempotentes)

> WIP — estou construindo isso pra mostrar que os patterns do Spring Boot
> transferem direto pra Django/DRF. Vou commitar incremental ao longo dos
> próximos dias.

## Stack

- Python 3.13
- Django 5.x + Django REST Framework
- PostgreSQL 16 + Redis 7 (via Docker Compose)
- Celery (async tasks)
- pytest-django (tests)

## Setup local

```bash
# 1. Sobe Postgres + Redis
docker compose up -d

# 2. Cria venv e instala deps
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Migrations + superuser
python manage.py migrate
python manage.py createsuperuser

# 4. Roda
python manage.py runserver
```

## Endpoints (Phase 1)

- `POST /api/auth/login/` — JWT (email + senha)
- `POST /api/auth/refresh/` — refresh token
- `GET /api/auctions/` — lista AuctionItems do tenant do user logado
- `POST /api/auctions/` — cria AuctionItem
- `POST /api/auctions/{id}/bid/` — registra bid (transação atômica)
- `GET /api/audit/{auction_id}/` — trail de alterações (Phase 2)

## Architecture notes

- **Tenant FK em todo model.** ViewSet sobrescreve `get_queryset()` pra
  filtrar `tenant=request.user.tenant`. Permission class garante que user
  só vê/edita resources do próprio tenant.
- **Bid race condition** — `transaction.atomic` + `select_for_update`
  no AuctionItem ao processar bid. Sem isso, dois usuários dando bid no
  mesmo item ao mesmo tempo podem zerar o highest_bid. Foi exatamente
  esse o bug que o LFAuctionHouse legacy tinha em JS.
- **AuditLog via signals** (Phase 2) — `post_save`/`post_delete` em
  AuctionItem e Bid gravam linha em AuditLog com user + tenant + diff.

## Status

- [x] Phase 0: setup do repo, deps, docker compose
- [ ] Phase 1: models multi-tenant + JWT + ViewSet CRUD
- [ ] Phase 2: AuditLog via signals + Celery task + tests
- [ ] Phase 3: deploy local docs + cheatsheet Spring↔Django no `/docs`

## Why this exists

Estou aplicando pra roles backend remoto LATAM e a maioria das vagas que
dão match com meu perfil (10 anos Java/Spring) usa Python/Django. Isso aqui
é a prova de que os patterns transferem direto — mesma arquitetura,
sintaxe diferente. Estimativa minha: 2-4 semanas de onboarding pra
produtividade plena num codebase Django de produção.

Trabalho relacionado (closed-source NDA):
- LoverCraft LLC (2021–present, US): plataforma real-time JVM, sole architect
- Senior Sistemas (2019–2024, BR): Spring Boot para Kinross Gold, Olfar, Grendene

Mais em [lucasfrederico.dev](https://lucasfrederico.dev).
