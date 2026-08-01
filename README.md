# financial-pbi

Pipeline de finanças pessoais com integração ao Google Sheets para:

- consolidar fluxo de caixa,
- processar receitas e despesas parceladas,
- calcular snapshots de patrimônio (CDI, BTC e outras criptos).

## Visão Rápida

![Python](https://img.shields.io/badge/Python-3.14+-blue)
![Pytest](https://img.shields.io/badge/tests-pytest-green)
![Status](https://img.shields.io/badge/status-active-success)

## Principais Funcionalidades

- Carga e normalização de múltiplas abas do Google Sheets.
- Processamento de fluxo de caixa consolidado com status (`Pago`, `Pendente`, etc.).
- Cálculo de patrimônio com:
    - CDI com série histórica Bacen,
    - BTC com conversão correta de satoshis,
    - Criptos por ticker usando CoinGecko.
- Escrita robusta no Sheets com:
    - estratégia de swap para snapshots,
    - append em lote para histórico incremental.
- Logging estruturado e retry com backoff exponencial.
- Testes automatizados com `pytest`.

## Arquitetura

```text
financial-pbi/
├── main.py
├── config.py
├── services/      # Integrações externas (Google Sheets)
├── processors/    # Regras de negócio
├── models/        # Dataclasses e contratos de dados
├── utils/         # Logging, retry, parsing e helpers
├── tests/         # Testes automatizados
└── modules/       # Compatibilidade com imports legados
```

## Requisitos

- Python 3.14+
- Acesso ao Google Sheets API com conta de serviço
- Arquivo `credentials.json` na raiz do projeto

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

Ajuste os parâmetros em `config.py`:

- `SPREADSHEET_ID`
- `MAX_RETRIES`, `RETRY_BASE_DELAY_SECONDS`, `REQUEST_TIMEOUT_SECONDS`
- `LOG_LEVEL`, `LOG_FILE`

Importante:

- `SATOSHIS_PER_BITCOIN` está definido como `100_000_000` (valor correto).
- `VENCIMENTO_CARTOES` define o dia de vencimento de cada cartão e é usado no cálculo de competência das compras.

## Execução

ETL / recálculo do Fluxo de Caixa (rodado pelo cron da VM e pelo `/run_script`):

```bash
python main.py
```

Bots (Telegram + Discord no mesmo processo):

```bash
python run_bots.py
```

Para rodar só um: `python -m bots.telegram_bot` ou `python -m bots.discord_bot`.
Configuração do Mini App do Telegram: ver `TELEGRAMBOT_SETUP.md`.

## Testes

```bash
pytest -q
```

## Contrato de Abas (Google Sheets)

### Entradas esperadas

| Aba | Finalidade |
| --- | --- |
| `FaturasPagas` | Último ciclo pago por cartão |
| `ComprasCartao` | Compras e parcelamentos no cartão |
| `PixParcelado` | Parcelamentos com entrada e parcelas |
| `Assinaturas` | Custos recorrentes |
| `DebitoAvulso` | Saídas à vista |
| `Receitas` | Entradas de caixa |
| `Investimentos` | Movimentações de CDI/BTC/cripto |

### Saídas geradas

| Aba | Conteúdo |
| --- | --- |
| `FluxoCaixaCompleto` | Movimentações consolidadas |
| `InvestimentoBTC` | Snapshot atual de BTC |
| `InvestimentoCripto` | Snapshot atual de criptos |
| `InvestimentoCDI` | Snapshot atual de CDI (`DataHora`) |

## O Que Mudou no Preenchimento da Planilha

- Fluxo de preenchimento manual continua praticamente o mesmo.
- Datas inválidas do tipo somente horário (ex.: `16:24:00`) agora são tratadas como vazias.
- `InvestimentoCDI` usa cabeçalho `DataHora` para preservar precisão temporal.
- Escrita incremental de investimentos é feita em lote (mais estável/performance).

## Observabilidade e Robustez

- Logs em console + arquivo (`logs/financial-pbi.log`).
- Retry padrão para chamadas externas com backoff exponencial.
- Tratamento de exceções específicas do `gspread` e requests.

## Módulos Principais

- `services/google_sheets.py`: leitura/escrita no Sheets.
- `processors/data_loader.py`: carga e normalização das abas.
- `processors/fluxo_caixa.py`: consolidação de entradas/saídas.
- `processors/patrimonio.py`: cálculo de snapshots de investimento.
- `utils/data_utils.py`: parsing de datas/números e cálculo de CDI.
- `utils/logging_config.py`: configuração de logging sem handlers duplicados.
- `utils/retry.py`: retry genérico com backoff.

## Troubleshooting

- Erro de credenciais: verifique `credentials.json` e permissões da conta de serviço.
- Erro de planilha: confirme `SPREADSHEET_ID` em `config.py`.
- Inconsistência de colunas: valide os cabeçalhos das abas de entrada.

## Licença

Uso pessoal.
