import json
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from utils.logging_config import get_logger

logger = get_logger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)

def interpretar_gasto_com_ia(texto_usuario: str) -> dict:
    prompt = f"""
    Extraia as informações da mensagem do usuário.
    Regras de Negócio:
    - tipo: "debito", "credito", "receita", "investimento" ou "pix". Se mencionar "pix parcelado", é "pix".
    - valor: extraia o número principal ou valor total (ex: 19.90, 50, 120).
    - conta_cartao: Opções (Inter, Nubank, MercadoPago). Se não informada, use "Inter".
    - categoria: Opções (Comida, iFood, Lazer, Vestuário, Utilidades, Presentes, Eletrônicos, Assinaturas, Saúde, Outros).
    - descricao: Resumo curto em Title Case.
    - parcelas: Inteiro. Padrão é 1.
    
    Regras exclusivas para INVESTIMENTOS:
    - tipo_investimento: Apenas (CDI, BTC, Cripto). Se não for investimento, use "N/A".
    - operacao: Apenas (Aporte, Saque). Se não for investimento, use "N/A".
    - quantidade_cripto: Número float. Padrão 0.0.
    
    Regras exclusivas para PIX PARCELADO:
    - valor_entrada: Número float. É o valor que foi pago na hora como entrada. Padrão 0.0.
    - qtd_pagas: Inteiro. Quantidade de parcelas que já foram pagas (geralmente 1 no momento da compra). Padrão 1.
    
    Mensagem: "{texto_usuario}"
    """
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "tipo": {"type": "STRING"},
            "valor": {"type": "NUMBER"},
            "conta_cartao": {"type": "STRING"},
            "categoria": {"type": "STRING"},
            "descricao": {"type": "STRING"},
            "parcelas": {"type": "INTEGER"},
            "tipo_investimento": {"type": "STRING"},
            "operacao": {"type": "STRING"},
            "quantidade_cripto": {"type": "NUMBER"},
            "valor_entrada": {"type": "NUMBER"},
            "qtd_pagas": {"type": "INTEGER"}
        },
        "required": [
            "tipo", "valor", "conta_cartao", "categoria", "descricao", 
            "parcelas", "tipo_investimento", "operacao", "quantidade_cripto",
            "valor_entrada", "qtd_pagas"
        ]
    }
    
    try:
        resposta = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            )
        )
        
        return json.loads(resposta.text)
        
    except Exception as e:
        logger.error(f"Erro no processamento da IA: {e}")
        return None