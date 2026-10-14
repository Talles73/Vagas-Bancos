# Vagas em bancos, corretoras e cooperativas

Página que mostra vagas coletadas **todo dia** automaticamente, com filtros de carreira, estado, cidade, tipo e nível.
Custo: R$ 0 (GitHub + plano gratuito da Adzuna).

## Como colocar no ar (cerca de 10 minutos)

1. **Chave da Adzuna (grátis):** crie conta em https://developer.adzuna.com e copie o `app_id` e o `app_key`.
2. **Repositório:** crie um repositório novo no GitHub (público) e envie todos os arquivos desta pasta
   (incluindo a pasta oculta `.github`). No site do GitHub: *Add file → Upload files* e arraste tudo.
3. **Segredos:** no repositório, vá em *Settings → Secrets and variables → Actions → New repository secret* e crie:
   - `ADZUNA_APP_ID`
   - `ADZUNA_APP_KEY`
4. **Primeira coleta:** aba *Actions → Atualizar vagas → Run workflow*. Em cerca de 2 minutos o arquivo `docs/vagas.json` é preenchido.
5. **Publicar a página:** *Settings → Pages → Branch: main, pasta /docs → Save*. O endereço aparece ali em seguida.

A partir daí a coleta roda sozinha todo dia às 06:00 (Brasília).

## Ajustes
- `collect.py`: lista de instituições (`INST`), buscas (`GENERIC`) e idade máxima das vagas (`MAX_DAYS_OLD`).
- `.github/workflows/atualizar.yml`: horário (`cron`, em UTC).

## Limites
- A Adzuna reúne anúncios de vários sites, mas não todos. Vagas que só existem nos portais oficiais dos bancos podem não aparecer; por isso a página tem os botões de busca direta (LinkedIn, Indeed, Gupy e site oficial).
- A coleta só guarda vagas cujo nome de empresa bate com a lista de instituições.
- O plano gratuito tem limite diário de chamadas; a coleta usa cerca de 100.
