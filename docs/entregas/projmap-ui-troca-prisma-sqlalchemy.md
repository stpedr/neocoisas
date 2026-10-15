# ProjMap UI — troca do ORM: Prisma → SQLAlchemy + Alembic

## Resumo
A decisão **D9** (ORM/banco pro catálogo da migração do frontend) foi
revista: em vez de `prisma-client-py`, o plano agora usa **SQLAlchemy 2.0
async + `aiosqlite`**, com **Alembic** pras migrações.

## Motivação
Pedido do usuário: trocar o Prisma por algo "mais próximo de algo mais
comercial open source". `prisma-client-py` é comunitário (não é o time da
Prisma que mantém o binding Python) e depende de um CLI em Node baixando um
binário Rust na primeira geração. SQLAlchemy é o ORM padrão do ecossistema
Python — muito mais adotado, mais mantido, sem nenhuma dependência de
toolchain fora do próprio `pip`.

## O que mudou
| Arquivo | Mudança |
|---|---|
| `docs/projmap/PLANO.md` | D9 revisada: SQLAlchemy + Alembic no lugar de `prisma-client-py`, com o porquê e o novo spike |
| `docs/entregas/projmap-ui-troca-prisma-sqlalchemy.md` | Este arquivo |

Nada de código de produção — `prisma`/`nodeenv`/`tomlkit` foram
desinstalados da `.venv-projmap` (não chegaram a entrar em
`requirements-projmap-master.txt`, então não havia nada a revogar lá).
`sqlalchemy[asyncio]`, `aiosqlite` e `alembic` foram instalados na venv para
o novo spike; entram em `requirements-projmap-master.txt` só na Fase 8, quando
o schema real for escrito.

## Como funciona
Repeti o mesmo teste de ponta a ponta do spike anterior, agora com
SQLAlchemy: `create_async_engine("sqlite+aiosqlite:///...")`, um modelo
declarativo (`DeclarativeBase` + `Mapped`/`mapped_column`), `create_all`
assíncrono, `insert`/`select` via `AsyncSession`. Funcionou de primeira, sem
nenhum passo de geração/CLI externo — só `pip install` e Python puro.

## Como validar
```bash
.venv-projmap/Scripts/python.exe -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
asyncio.run(create_async_engine('sqlite+aiosqlite:///:memory:').connect())
print('ok')
"
```
`pytest -q` não muda (nenhum código de produção foi tocado): continua 464
verdes.

## Critério de aceite
- [x] SQLAlchemy async + aiosqlite funciona nativo no Windows, sem Docker, sem binário externo
- [x] Decisão revista registrada em D9 (`docs/projmap/PLANO.md`)
- [x] `prisma`/`nodeenv`/`tomlkit` removidos da venv; nada em requirements a revogar
- [x] `pytest -q` segue verde (464)

## Pendências / próximos
- O schema real (`Show`, biblioteca, presets, histórico) continua previsto
  pra Fase 8 do plano de migração — só a ferramenta trocou, o escopo não.
- Alembic entra junto na Fase 8 (`alembic init`, primeira revisão).
