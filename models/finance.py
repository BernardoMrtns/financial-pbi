from dataclasses import asdict, dataclass
from typing import Any, Dict

import pandas as pd


@dataclass
class Movimentacao:
    data_original: pd.Timestamp
    data_competencia: pd.Timestamp
    tipo: str
    metodo: str
    conta_cartao: str
    categoria: str
    descricao: str
    valor: float
    status: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return {
            "DataOriginal": payload["data_original"],
            "DataCompetencia": payload["data_competencia"],
            "Tipo": payload["tipo"],
            "Metodo": payload["metodo"],
            "Conta_Cartao": payload["conta_cartao"],
            "Categoria": payload["categoria"],
            "Descricao": payload["descricao"],
            "Valor": payload["valor"],
            "Status": payload["status"],
        }
