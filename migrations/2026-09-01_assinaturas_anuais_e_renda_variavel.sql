-- Assinaturas anuais + ETFs e acoes da B3.
--
-- O projeto nao tem ferramenta de migracao: as tabelas nascem de pandas.to_sql
-- e o DDL e aplicado a mao. Rode este arquivo no psql ou cole os comandos no
-- /sql do bot, na ordem em que aparecem.
--
-- ATENCAO: rodar bootstrap_pg.py depois disto recria as tabelas com
-- if_exists='replace' e apaga tudo o que esta aqui.

-- ---------------------------------------------------------------------------
-- 0. Conferencia previa. O RENAME do passo 2 quebra se ja existir uma coluna
--    "quantidade" legada em investimentos.
-- ---------------------------------------------------------------------------
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('investimentos', 'assinaturas')
ORDER BY table_name, ordinal_position;

-- ---------------------------------------------------------------------------
-- 1. Assinaturas: periodicidade de cobranca.
--    Todas as assinaturas existentes hoje sao mensais.
-- ---------------------------------------------------------------------------
ALTER TABLE assinaturas ADD COLUMN IF NOT EXISTS periodicidade text;

UPDATE assinaturas
SET periodicidade = 'Mensal'
WHERE periodicidade IS NULL OR btrim(periodicidade) = '';

-- ---------------------------------------------------------------------------
-- 2. Investimentos: classe do ativo + rename da quantidade.
--    "tipo" continua sendo o ticker (CDI, BTC, ETH, BOVA11, PETR4);
--    "classe" e o discriminador que decide a fonte da cotacao.
-- ---------------------------------------------------------------------------
ALTER TABLE investimentos ADD COLUMN IF NOT EXISTS classe text;

UPDATE investimentos
SET classe = CASE WHEN upper(tipo) = 'CDI' THEN 'CDI' ELSE 'Cripto' END
WHERE classe IS NULL OR btrim(classe) = '';

-- Se o passo 0 mostrou que "quantidade" NAO existe, use o rename:
ALTER TABLE investimentos RENAME COLUMN quantidade_cripto TO quantidade;

-- Se "quantidade" JA existia, comente a linha acima e use estas tres no lugar:
-- UPDATE investimentos
-- SET quantidade = quantidade_cripto
-- WHERE COALESCE(quantidade, 0) = 0 AND COALESCE(quantidade_cripto, 0) <> 0;
-- ALTER TABLE investimentos DROP COLUMN quantidade_cripto;

-- ---------------------------------------------------------------------------
-- 3. Snapshot de renda variavel. O ETL cria a tabela sozinho no primeiro
--    "python main.py" (pandas.to_sql), mas criar aqui garante os tipos certos
--    e a chave primaria que o Power BI descarta na query M.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investimento_renda_variavel (
    id           SERIAL PRIMARY KEY,
    data_hora    TIMESTAMP     NOT NULL,
    ticker       TEXT          NOT NULL,
    ativo        TEXT,
    classe       TEXT          NOT NULL,
    saldo_cotas  DOUBLE PRECISION,
    preco_cota   NUMERIC(18, 6),
    valor_reais  NUMERIC(18, 2)
);

CREATE INDEX IF NOT EXISTS idx_inv_rv_data_hora
    ON investimento_renda_variavel (data_hora DESC);

-- ---------------------------------------------------------------------------
-- 4. Conferencia final.
-- ---------------------------------------------------------------------------
SELECT periodicidade, count(*) FROM assinaturas GROUP BY periodicidade;
SELECT classe, count(*) FROM investimentos GROUP BY classe;
