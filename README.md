# Sistema de Controle Financeiro

Sistema modular para gerenciamento de finanças pessoais integrado com Google Sheets.

## Estrutura do Projeto

```
projeto_financas/
├── main.py                      # Script principal
├── config.py                    # Configurações centralizadas
├── requirements.txt             # Dependências do projeto
├── credentials.json             # Credenciais Google (não commitado)
└── modules/
    ├── __init__.py             # Inicializador do módulo
    ├── google_sheets.py        # Integração com Google Sheets
    ├── data_loader.py          # Carregamento de dados
    ├── data_processor.py       # Processamento de fluxo de caixa
    ├── patrimonio.py           # Cálculo de patrimônio
    └── utils.py                # Funções utilitárias
```

## Instalação

```bash
pip install -r requirements.txt
```

## Configuração

1. Coloque seu arquivo `credentials.json` na raiz do projeto
2. Edite `config.py` com seu `SPREADSHEET_ID`
3. Ajuste `DIA_FECHAMENTO_CARTAO` se necessário

## Uso

Execute o script principal:

```bash
python main.py
```

## Módulos

### config.py
Configurações centralizadas do sistema (credenciais, IDs, schemas).

### modules/google_sheets.py
- `conectar_google_sheets()`: Conecta ao Google Sheets
- `carregar_aba()`: Carrega uma aba como DataFrame
- `salvar_aba()`: Salva DataFrame em uma aba

### modules/utils.py
- `converter_data_flexivel()`: Converte datas em múltiplos formatos
- `calcular_mes_competencia()`: Calcula mês de competência do cartão
- `obter_cdi_historico()`: Busca histórico de CDI

### modules/data_loader.py
Classe `DataLoader`: Carrega e normaliza todas as abas do Google Sheets.

### modules/data_processor.py
Classe `FluxoCaixaProcessor`: Processa movimentações:
- Cartões de crédito (parcelado)
- PIX parcelado
- Assinaturas recorrentes
- Débitos e receitas
- Investimentos

### modules/patrimonio.py
Classe `PatrimonioCalculator`: Calcula evolução de patrimônio:
- CDI (corrigido diariamente)
- Bitcoin (com lógica exclusiva)
- Criptomoedas genéricas por ticker (ex.: SOL, XRP, ETH)

## Abas do Google Sheets

**Entrada:**
- FaturasPagas
- ComprasCartao
- PixParcelado
- Assinaturas
- DebitoAvulso
- Receitas
- Investimentos

**Saída:**
- FluxoCaixaCompleto
- InvestimentoBTC
- InvestimentoBTC_Historico
- InvestimentoCripto
- InvestimentoCripto_Historico
- InvestimentoCDI
