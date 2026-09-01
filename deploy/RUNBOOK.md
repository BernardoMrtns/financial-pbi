# Runbook da VM

Referência operacional do `financial-pbi` em produção. Escrito durante a
migração de 01/09/2026 (assinaturas anuais + renda variável).

## Fatos da máquina

| | |
|---|---|
| Host | Oracle Cloud, `telegram-financial-bot-vnic` — IP e chave no gerenciador de senhas |
| Acesso | `ssh -i <chave> ubuntu@<ip>` |
| Projeto | **`/opt/financial-pbi`** |
| venv | `/opt/financial-pbi/venv` (Python 3.14) |
| Serviço | **`financial-bots.service`** — plural |
| Postgres | 14.24, local, base `financial_db` |
| ETL | cron do `ubuntu`, de hora em hora no minuto 0, com `flock` |
| Backup | cron do `ubuntu`, domingo 23:59 → `/home/ubuntu/postgres_backups/` |

O repositorio e **publico** (requisito do GitHub Pages para o Mini App). Nao
comite IP, chave, senha ou token aqui.

### Duas armadilhas de nome

- O serviço é **`financial-bots`**, não `financial-bot`. `systemctl stop financial-bot`
  retorna sucesso aparente mas o unit é `not-found` — o bot **continua rodando**.
- O projeto está em **`/opt/financial-pbi`**. Não existe `/home/ubuntu/financial-pbi`
  nem `/home/ubuntu/opt/financial-pbi`; um `scp` para lá cria um arquivo órfão que
  ninguém lê.

## Comandos do dia a dia

```bash
sudo systemctl status financial-bots.service
```

```bash
sudo journalctl -u financial-bots.service -f
```

```bash
sudo -u postgres psql -d financial_db
```

Rodar o ETL na mão (o `/run_script` do bot faz o mesmo):

```bash
cd /opt/financial-pbi && ./venv/bin/python main.py
```

## config.py

É **gitignored** e vive só na VM — `git pull` nunca o toca. As credenciais de
Telegram da VM **são diferentes** das da máquina local, então **nunca faça
`scp` do config.py local por cima**: isso troca o bot de produção por outro.
Edite no lugar, sempre com backup antes:

```bash
cp /opt/financial-pbi/config.py /home/ubuntu/config.py.bak-$(date +%Y%m%d_%H%M%S)
```

## Deploy de uma mudança

Assumindo que o commit já está no `origin/main`.

> **Ordem importa.** Não existe janela em que código novo e schema velho (ou
> vice-versa) convivam: código novo escreve colunas que não existem, código
> velho escreve colunas que sumiram. Por isso o serviço para primeiro.
>
> O Mini App é servido pelo **GitHub Pages a partir de `docs/` no `main`**, ou
> seja, ele atualiza no `git push`, não no deploy da VM. Entre o push e o
> restart, o app novo manda campos que o bot velho ignora — e grava **errado em
> silêncio** (assinatura com dia 1, investimento com quantidade 0). Parar o
> serviço no passo 1 é o que fecha essa janela.

```bash
sudo systemctl stop financial-bots.service
```

Desligar o ETL durante a janela (ele roda de hora em hora):

```bash
crontab -l > /tmp/crontab.bak && crontab -l | sed 's|^0 \* \* \* \* flock|#MIGRACAO# &|' | crontab -
```

Backup verificado — **faça sempre**, é o único ponto de retorno:

```bash
/home/ubuntu/backup_db.sh
```

Atualizar o código e conferir:

```bash
cd /opt/financial-pbi && git pull --ff-only && ./venv/bin/python -m pytest tests/ -q
```

Aplicar o DDL, se houver. Rode **dentro de uma transação** (`BEGIN; ... COMMIT;`)
com as conferências antes do `COMMIT`, para poder abortar sem estrago.

Validar antes de reabrir:

```bash
cd /opt/financial-pbi && ./venv/bin/python main.py
```

Reabrir o sistema:

```bash
crontab -l | sed 's|^#MIGRACAO# ||' | crontab - && sudo systemctl start financial-bots.service
```

## Backups

`deploy/backup_db.sh` (instalado em `/home/ubuntu/backup_db.sh`) usa autenticação
**peer** via `sudo -u postgres` — sem senha em lugar nenhum — grava num temporário,
valida com `pg_restore -l` e só então publica o arquivo final. Mantém os 8 mais
recentes.

Restaurar:

```bash
sudo -u postgres pg_restore -d financial_db --clean --if-exists /home/ubuntu/postgres_backups/ARQUIVO.dump
```

## Credenciais

Vivem **apenas** no `config.py` da VM (gitignored) e no seu gerenciador de senhas.
O Power BI guarda a senha do Postgres no cofre do proprio Windows, nao no `.pbip`.

Ao rotacionar a senha do banco, os quatro pontos precisam ser atualizados juntos:

1. `ALTER ROLE admin_finance WITH PASSWORD '<nova>';`
2. `DB_URL` no `config.py` da VM
3. `DB_URL` no `config.py` da maquina local
4. Power BI Desktop, na proxima atualizacao (ele volta a pedir)

O `backup_db.sh` nao entra na lista: usa auth peer e nao conhece senha.

> **Histórico:** de 17/05 a 30/08/2026 os 16 backups semanais saíram com **0 bytes**.
> O cron usava `PGPASSWORD='senha'` (literal), o `pg_dump` falhava e o `>` criava o
> arquivo vazio mesmo assim — falha silenciosa por 3 meses e meio. Daí a validação
> obrigatória no script novo. **Confira o tamanho de vez em quando:**

```bash
ls -lah /home/ubuntu/postgres_backups/
```

## Sequences de id

`bootstrap_pg.py` cria a coluna `id SERIAL` **depois** de popular a tabela, o que
deixa a sequence atrás do `max(id)`. O sintoma é `duplicate key value violates
unique constraint` na primeira inserção pelo bot — e só nela. O passo 4 da
migração de 01/09/2026 ressincroniza todas de uma vez e é idempotente; reaproveite
esse bloco sempre que uma tabela for repovoada fora do fluxo normal.

## O que é derivado e o que é insubstituível

- **Insubstituível** — as tabelas de entrada (`assinaturas`, `investimentos`,
  `compras_cartao`, `pix_parcelado`, `debito_avulso`, `receitas`, `faturas_pagas`)
  e os snapshots append-only (`investimento_cdi`, `investimento_btc`,
  `investimento_cripto`, `investimento_renda_variavel`), que são cotações de
  mercado em pontos no tempo e não podem ser recalculadas.
- **Derivado** — `fluxo_caixa` é reconstruído do zero a cada ETL. Se corromper,
  basta rodar `main.py`.

> `atualizar_tabela_completa()` faz `TRUNCATE` e o `append` vem numa transação
> **separada**: se o append falhar, `fluxo_caixa` fica vazia. Não é perda real
> (é derivada), mas explica uma tabela subitamente zerada.

## Nunca rode em produção

`bootstrap_pg.py` — usa `to_sql(if_exists='replace')`, que **dropa e recria**
todas as tabelas, e não conhece nenhuma coluna criada depois dele (ver
`migrations/`). Desde 01/09/2026 ele exige `BOOTSTRAP_DB_URL` explícita, sem
valor padrão, justamente para tornar um disparo acidental impossível.
