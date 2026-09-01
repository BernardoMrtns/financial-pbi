#!/usr/bin/env bash
# Backup do financial_db. Autenticacao peer via postgres: sem senha em lugar nenhum.
# So publica o arquivo final se o dump tiver conteudo E abrir no pg_restore --
# o cron antigo usava "> arquivo" direto e deixava 0 bytes quando o dump falhava.
set -euo pipefail
cd /tmp

DEST=/home/ubuntu/postgres_backups
RETENCAO=8
mkdir -p "$DEST"

TMP=$(mktemp /tmp/financial_db.XXXXXX.dump)
trap 'rm -f "$TMP"' EXIT

sudo -n -u postgres pg_dump -Fc financial_db > "$TMP"

if [ ! -s "$TMP" ]; then
    echo "$(date -Is) FALHA: dump vazio" >&2
    exit 1
fi
pg_restore -l "$TMP" > /dev/null

mv "$TMP" "$DEST/financial_db_$(date +%F).dump"
trap - EXIT

echo "$(date -Is) OK $(du -h "$DEST/financial_db_$(date +%F).dump" | cut -f1)"

# Retencao: mantem os mais recentes, descarta o excedente.
ls -1t "$DEST"/financial_db_*.dump 2>/dev/null | tail -n +$((RETENCAO + 1)) | xargs -r rm -f
