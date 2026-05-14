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
    Regras de Negócio OBRIGATÓRIAS:
    - tipo: "debito", "credito", "receita", "investimento", "pix" ou "wishlist".
      * ATENÇÃO: Se a mensagem contiver "parcelado", "vezes", "parcelei" ou "cartão", OBRIGATORIAMENTE o tipo é "credito" (a menos que diga explicitamente "pix parcelado").
      * Se falar "quero comprar", "vontade" ou "desejo", é "wishlist".
    - valor: extraia o número principal ou valor total da compra (ex: 19.90, 50, 120).
    - conta_cartao: Opções (Inter, Nubank, MercadoPago). Se não informada, use "Inter".
    - categoria: Opções (Comida, iFood, Lazer, Vestuário, Utilidades, Presentes, Eletrônicos, Assinaturas, Saúde, Outros).
    - descricao: Resumo curto em Title Case.
    - parcelas: Número inteiro. Se falar a quantidade de vezes (ex: "4 vezes", "em 4x", "parcelei de 4"), extraia esse número. Padrão é 1.
    
    Regras exclusivas para INVESTIMENTOS:
    - tipo_investimento: Apenas (CDI, BTC, Cripto). Padrão "N/A".
    - operacao: Apenas (Aporte, Saque). Padrão "N/A".
    - quantidade_cripto: Número float. Padrão 0.0.
    
    Regras exclusivas para PIX PARCELADO:
    - valor_entrada: Número float. Padrão 0.0.
    - qtd_pagas: Inteiro. Padrão 1.
    
    Regras exclusivas para WISHLIST:
    - prioridade: String. Opções (High, Mid, Low). Padrão "Mid".
    
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
            "qtd_pagas": {"type": "INTEGER"},
            "prioridade": {"type": "STRING"}
        },
        "required": [
            "tipo", "valor", "conta_cartao", "categoria", "descricao", 
            "parcelas", "tipo_investimento", "operacao", "quantidade_cripto",
            "valor_entrada", "qtd_pagas", "prioridade"
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