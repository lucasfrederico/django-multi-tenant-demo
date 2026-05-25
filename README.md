# django-multi-tenant-demo

Pequeno serviço Django + DRF que recria, em Python, os patterns que rodei
em produção por 5 anos numa plataforma real-time na JVM:

- **Multi-tenancy** com FK por tenant + queryset filter (mesma estratégia
  de isolamento que usei numa rede com 1.500 usuários simultâneos, sub-50ms
  no hot path)
- **Audit trail** automático via Django signals + thread-local pra capturar
  o user do request
- **JWT auth** (djangorestframework-simplejwt), com uma subclass custom que
  popula o thread-local logo após validar o token
- **Async tasks** com Celery + Redis (equivalente a RabbitMQ que usei no
  LoverCraft pra side-effects pós-bid)
- **AuctionItem + Bids** como domínio — porque foi o feature mais hairy do
  meu trabalho real (LFAuctionHouse: refatorei 2.800 linhas de JS legacy
  num serviço Java com invariants idempotentes e `select_for_update` em
  bid concorrente)

> Estou aplicando pra roles Senior Backend remoto LATAM e a maioria das
> vagas decentes usa Python/Django. Isso aqui é a prova de que os patterns
> transferem direto — mesma arquitetura, sintaxe diferente.

## Stack

- Python 3.13 · Django 5.1 · DRF 3.15
- PostgreSQL 16 + Redis 7 (via Docker Compose)
- Celery 5.4 (async tasks, eager em tests)
- pytest-django 4.9 (11 tests, 100% passando)

## Setup local

```bash
# 1. Sobe Postgres + Redis
docker compose up -d

# 2. venv + deps
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. .env e migrations
cp .env.example .env
python manage.py migrate

# 4. (opcional) seed de dev — cria 2 tenants, 3 users, 1 leilão com bids
python manage.py shell < scripts/seed_dev.py

# 5. Roda a API
python manage.py runserver
```

Em outro terminal, sobe o worker Celery:

```bash
celery -A config worker -l info
```

## Rodando os tests

```bash
pytest                      # 11 tests, ~1.5s
pytest -k tenant            # só os de isolamento
pytest --cov=apps           # com coverage
```

Os tests usam `CELERY_TASK_ALWAYS_EAGER=True` — task `notify_outbid`
roda inline na thread do test, sem precisar de worker Celery rodando.

## API — exemplos curl

Login com user do seed:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@acme.test","password":"alice123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access'])")
```

Listar leilões do tenant (queryset filter automático):

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/auctions/
```

Criar leilão (tenant + created_by injetados server-side):

```bash
curl -s -X POST http://localhost:8000/api/auctions/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Painting",
    "starting_price": "500.00",
    "status": "active",
    "closes_at": "2026-06-01T00:00:00Z"
  }'
```

Dar bid (transação atômica + signal grava audit + Celery task dispatched):

```bash
curl -s -X POST http://localhost:8000/api/auctions/1/bid/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": "550.00"}'
```

## Architecture notes

### Multi-tenant via queryset filter

Cada model carrega FK direto pro Tenant (não só via User). Isso permite
filter sem JOIN extra:

```python
def get_queryset(self):
    tenant_id = getattr(self.request.user, "tenant_id", None)
    if tenant_id is None:
        return AuctionItem.objects.none()
    return AuctionItem.objects.filter(tenant_id=tenant_id)
```

`IsSameTenant` permission class é defesa em profundidade pra `retrieve`
direto por ID (já pegou via queryset, mas se algum dev quebrar o filter
sem querer, a permission ainda barra).

**Quando esse pattern QUEBRA:** signals nativos do Django (`post_save`)
não conhecem o request — o thread-local resolve isso (ver abaixo).

### Race condition em bid concorrente

Dois users dando bid no mesmo leilão ao mesmo tempo é o problema clássico
TOCTOU:

```
T1 lê current_price=100
T2 lê current_price=100
T1 escreve current_price=110 ✓
T2 escreve current_price=120 ✓
T1 perdeu (overwrite silencioso)
```

Solução: `select_for_update` dentro de `transaction.atomic` no AuctionItem:

```python
with transaction.atomic():
    auction = AuctionItem.objects.select_for_update().filter(...).first()
    # T2 espera T1 commitar antes de chegar aqui
    if amount <= (auction.current_price or auction.starting_price):
        return 400
    Bid.objects.create(...)
    auction.current_price = amount
    auction.save()
```

Foi exatamente esse o bug no LFAuctionHouse legacy (JavaScript single-thread
mas com `await` mal escrito). Em Java fizemos com `SELECT ... FOR UPDATE`
em transação serializable. Em Django/Postgres, o pattern é literal o mesmo.

### Audit trail via signals + thread-local

`post_save` / `post_delete` em AuctionItem e Bid disparam um receiver
que grava AuditLog. Mas signals não recebem `request` — como pegar quem
fez a ação?

**Não usei** middleware Django simples — `request.user` ainda é
`AnonymousUser` quando o middleware roda (DRF resolve JWT só dentro da
view, em `initial()`).

**Solução:** subclassar `JWTAuthentication` e armazenar o user no
thread-local logo após o `super().authenticate()` retornar:

```python
class JWTAuthCapturesCurrentUser(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _ = result
            _state.user = user
        return result
```

Os signals leem `get_current_user()` do thread-local. Para ações fora de
request (Django shell, Celery task), o thread-local fica vazio → audit
log com `actor=NULL` = "ação de sistema". É o pattern certo.

### `current_price` denormalizado

Em vez de calcular `max(Bid.amount)` em todo GET, o AuctionItem carrega
`current_price` direto. Trade-off:

- **Read fica O(1)** (vs O(n_bids) se aggregate)
- **Write precisa estar em transação** (já está — vai junto com o INSERT
  do Bid)

Em produção: índice em `(auction_id, -amount)` em Bid pra fallback caso
o denormalizado fique inconsistente.

### Por que NÃO django-tenants (schema-per-tenant)

Considerei. Decidi não usar porque:
1. Esquema único é mais simples de operar (1 migration set, 1 backup)
2. Para o tipo de produto que estou demonstrando (B2B SaaS pequeno-médio),
   o boundary lógico (FK filter) é suficiente
3. Em produção, se compliance exigir isolation física, o pattern do
   queryset filter ainda funciona — só troca a strategy de storage embaixo

Schema-per-tenant valeria pra: financial services com auditoria regulatória,
multi-tenant onde 1 cliente pode trazer 90% do tráfego (problema de noisy
neighbor que só schema isolation resolve).

## Spring Boot ↔ Django cheatsheet

| Spring Boot | Django |
|---|---|
| `@RestController` | DRF `ViewSet` |
| Hibernate / JPA | Django ORM |
| Flyway migrations | Django migrations |
| Spring Security RBAC | `permissions.py` + DRF permission classes |
| Spring AOP middleware | Django middleware |
| Spring Events | Django signals |
| `@Async` / `@Scheduled` | Celery tasks + Celery beat |
| `application.yml` | `settings.py` + `.env` |
| Maven / Gradle | pip / Poetry |
| `@Transactional` | `transaction.atomic()` |
| `SELECT ... FOR UPDATE` | `queryset.select_for_update()` |

## Status

- [x] Phase 0: setup do repo, deps, Docker Compose
- [x] Phase 1: models multi-tenant + JWT + ViewSet com queryset filter + bid endpoint atômico
- [x] Phase 2: AuditLog via signals + Celery task + 11 tests passando
- [ ] Phase 3: OpenAPI schema (drf-spectacular) + admin polish + docs `/docs`

## Why this exists

Estou aplicando pra roles Senior Backend remoto LATAM e a maioria das
vagas que dão match com meu perfil (10 anos Java/Spring) está em Python/Django.
Esse repo é a prova de que os patterns transferem direto — mesma
arquitetura, sintaxe diferente.

**Trabalho relacionado (closed-source NDA):**
- LoverCraft LLC (2021–presente, US): plataforma real-time JVM, sole architect, 1.500 concurrent users
- Senior Sistemas (2019–2024, BR): Spring Boot para Kinross Gold, Olfar, Grendene

Mais em [lucasfrederico.dev](https://lucasfrederico.dev).
