import pandas as pd
import ollama
from datetime import datetime
from sqlalchemy import create_engine, text
from config import DB_URL
from utils.logging_config import get_logger

logger = get_logger(__name__)

def gerar_insight_financeiro():
    print("[1] Conectando ao PostgreSQL na VM...")
    
    try:
        engine = create_engine(DB_URL)
    except Exception as e:
        logger.error(f"Erro ao conectar no banco de dados: {e}")
        return

    mes_atual = datetime.now().strftime("%Y-%m")
    
    # Mantivemos a sua correção exata da variável "data_competencia" minúscula
    query = f"""
        SELECT * FROM fluxo_caixa 
        WHERE CAST("data_competencia" AS TEXT) LIKE '{mes_atual}%'
    """
    
    try:
        with engine.connect() as conn:
            df_mes = pd.read_sql(text(query), conn)
            
    except Exception as e:
        logger.error(f"Falha ao ler a tabela do fluxo de caixa: {e}")
        return

    if df_mes.empty:
        print(f"[AVISO] Nenhum dado financeiro encontrado para o mês {mes_atual}.")
        return

    # Padroniza os nomes das colunas e os textos para evitar erros
    df_mes.columns = [c.lower() for c in df_mes.columns]
    if 'tipo' in df_mes.columns:
        df_mes['tipo'] = df_mes['tipo'].str.lower()
    if 'categoria' in df_mes.columns:
        df_mes['categoria'] = df_mes['categoria'].str.lower()
        
    # Separa Entradas e Saídas
    df_receitas = df_mes[df_mes['tipo'].isin(['entrada', 'receita'])]
    df_saidas = df_mes[df_mes['tipo'].isin(['saida', 'despesa'])]
    
    # Isola os Investimentos dos Gastos Reais (Custo de Vida)
    mask_investimento = df_saidas['categoria'].str.contains('investimento', na=False)
    
    total_receitas = df_receitas['valor'].sum()
    total_investido = df_saidas[mask_investimento]['valor'].sum()
    total_despesas_reais = df_saidas[~mask_investimento]['valor'].sum()
    
    # Saldo livre: O que sobra depois de pagar as contas E fazer os aportes
    saldo_livre = total_receitas - total_despesas_reais - total_investido
    
    # Mantendo o seu pedido do Top 5 categorias (Excluindo a categoria Investimento)
    top_gastos = df_saidas[~mask_investimento].groupby('categoria')['valor'].sum().nlargest(5)
    
    print("[2] Enviando contexto para a Inteligência Artificial Local (Qwen 14b) na GPU...")
    
    prompt = f"""
    [SYSTEM ROLE]
    Você é um analista financeiro direto, analítico e pragmático.

    Seu trabalho é olhar os números do mês e gerar um comentário curto, inteligente e objetivo sobre comportamento financeiro, concentração de gastos e eficiência dos aportes.

    [OBJETIVO]
    Gerar um insight financeiro curto com foco em:
    - percentuais;
    - concentração de despesas;
    - eficiência de investimento;
    - leitura prática dos números.

    [REGRAS]
    - Calcule implicitamente:
    - percentual investido sobre receita;
    - percentual de cada gasto relevante sobre a receita total.
    - Destaque categorias que estejam consumindo parcela relevante da renda.
    - Se os aportes estiverem altos, reconheça isso.
    - Saldo livre baixo NÃO é problema se os investimentos estiverem fortes.
    - Fale como alguém analisando um dashboard financeiro pessoal.
    - Pode soar levemente provocativo ou irônico.
    - Priorize números e impacto percentual.
    - Seja específico.

    [ESTILO]
    - Linguagem natural.
    - Frases curtas.
    - Tom direto.
    - Sem corporativês.
    - Sem linguagem de coach.
    - Sem parecer relatório empresarial.

    [PROIBIDO]
    - Textão.
    - Educação financeira genérica.
    - Linguagem formal demais.
    - Frases como:
    "estrutura financeira",
    "eficiência patrimonial",
    "crescimento patrimonial",
    "recomenda-se",
    "observa-se".

    [FORMATO]
    - Apenas 1 parágrafo.
    - Máximo de 3 frases.
    - PT-BR natural.
    - Texto puro.

    [DADOS]
    Receita Total: R$ {total_receitas:.2f}
    Total Investido: R$ {total_investido:.2f}
    Total Gasto: R$ {total_despesas_reais:.2f}
    Saldo Livre: R$ {saldo_livre:.2f}

    [TOP GASTOS]
    {top_gastos.to_string()}

    [EXEMPLOS]

    "Tu converteu quase metade da renda em aporte esse mês, então o saldo baixo na conta não preocupa muito. Vestuário já tá puxando X% da receita e eletrônicos Y%, dois gastos que começaram a pesar mais do que deveriam."

    "Aporte veio forte esse mês, mas eletrônicos sozinho já consumiu uma fatia agressiva da renda. O dinheiro tá indo mais pra upgrade de setup do que deveria."

    "Investimento encaixou bem no mês, mas vestuário e delivery juntos já estão começando a competir com os aportes. Vale ficar de olho nisso."
    """

    try:
        resposta = ollama.chat(
            model='qwen2.5:14b', 
            messages=[{'role': 'user', 'content': prompt}]
        )
        insight_texto = resposta['message']['content'].strip()
        print(f"\n[INSIGHT GERADO]:\n{insight_texto}\n")
    except Exception as e:
        logger.error(f"Erro na geração da IA com Ollama: {e}")
        return
    
    print("[3] Salvando o insight no PostgreSQL (tabela 'insights_ia')...")
    
    # Atualizado para salvar as colunas corretas separando investimento e gasto real
    df_insight = pd.DataFrame({
        'data_geracao': [datetime.now()],
        'mes_referencia': [mes_atual],
        'total_receitas': [total_receitas],
        'total_despesas_reais': [total_despesas_reais],
        'total_investido': [total_investido],
        'saldo_livre': [saldo_livre],
        'insight_texto': [insight_texto]
    })
    
    try:
        # Escreve de volta no PostgreSQL. O Pandas cria a tabela automaticamente se não existir.
        df_insight.to_sql('insights_ia', engine, if_exists='append', index=False)
        print("[SUCESSO] Insight gravado no banco de dados com sucesso!")
        print("-> Agora é só ir no Power BI, importar a tabela 'insights_ia' e criar seu card de narrativa!")
    except Exception as e:
        logger.error(f"Falha ao salvar no banco PostgreSQL: {e}")

if __name__ == "__main__":
    gerar_insight_financeiro()