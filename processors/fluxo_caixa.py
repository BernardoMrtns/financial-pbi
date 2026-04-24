from __future__ import annotations

from typing import Any

import pandas as pd
from pandas.tseries.offsets import DateOffset

from config import (
    STATUS_AGUARDANDO_FATURA,
    STATUS_PAGO,
    STATUS_PENDENTE,
    STATUS_RECEBIDO,
    TIPO_ENTRADA,
    TIPO_SAIDA,
)
from models import Movimentacao
from utils import calcular_mes_competencia, get_logger

logger = get_logger(__name__)


class FluxoCaixaProcessor:
    def __init__(self, dados: dict[str, Any], mapa_pagamentos: dict[str, pd.Timestamp]):
        self.dados = dados
        self.mapa_pagamentos = mapa_pagamentos
        self.lista_movimentacoes: list[Movimentacao] = []

    def processar_todas_movimentacoes(self) -> pd.DataFrame:
        logger.info("Processando fluxo de caixa")

        self.processar_cartao()
        self.processar_pix_parcelado()
        self.processar_assinaturas()
        self.processar_debitos()
        self.processar_receitas()
        self.processar_investimentos()

        return self._consolidar_movimentacoes()

    def processar_cartao(self) -> None:
        df_compras = self.dados["compras"]

        for r in df_compras.itertuples():
            data = r.Data
            if pd.isna(data):
                continue

            total = float(r.ValorTotal)
            n_parc = int(r.Parcelas) if pd.notna(r.Parcelas) and r.Parcelas != "" else 1
            primeira_fat = calcular_mes_competencia(data, getattr(r, "Cartao", ""))
            if pd.isna(primeira_fat):
                continue

            valor_base = round(total / n_parc, 2)
            valores = [valor_base] * n_parc
            valores[-1] = round(total - sum(valores[:-1]), 2)

            for i in range(n_parc):
                mes_ref = (primeira_fat + DateOffset(months=i)).to_period("M").to_timestamp()
                self.lista_movimentacoes.append(
                    Movimentacao(
                        data_original=data,
                        data_competencia=mes_ref,
                        tipo=TIPO_SAIDA,
                        metodo="Cartao de Credito",
                        conta_cartao=getattr(r, "Cartao", ""),
                        categoria=getattr(r, "Categoria", ""),
                        descricao=f"{getattr(r, 'Descricao', '')} ({i + 1}/{n_parc})",
                        valor=valores[i],
                        status=STATUS_AGUARDANDO_FATURA,
                    )
                )

    def processar_pix_parcelado(self) -> None:
        df_pix = self.dados["pix"]
        df_pix["QtdPagas"] = pd.to_numeric(df_pix["QtdPagas"], errors="coerce").fillna(0).astype(int)
        df_pix["ValorEntrada"] = pd.to_numeric(df_pix["ValorEntrada"], errors="coerce").fillna(
            df_pix["ValorTotal"] / 4
        )

        for r in df_pix.itertuples():
            data = r.Data
            if pd.isna(data):
                continue

            total = float(r.ValorTotal)
            entrada = float(r.ValorEntrada)
            qtd_pagas = int(r.QtdPagas)
            saldo = total - entrada
            valores = [
                entrada,
                round(saldo / 3, 2),
                round(saldo / 3, 2),
                round(total - (entrada + 2 * round(saldo / 3, 2)), 2),
            ]

            for i in range(4):
                num = i + 1
                vencimento = data + pd.DateOffset(days=15 * i)
                mes_ref = vencimento.to_period("M").to_timestamp()
                pago = (num <= qtd_pagas) or (vencimento <= pd.Timestamp.now())

                self.lista_movimentacoes.append(
                    Movimentacao(
                        data_original=data,
                        data_competencia=mes_ref,
                        tipo=TIPO_SAIDA,
                        metodo="Pix Parcelado",
                        conta_cartao="Conta Corrente",
                        categoria=getattr(r, "Categoria", ""),
                        descricao=f"{getattr(r, 'Descricao', '')} ({num}/4)",
                        valor=valores[i],
                        status=STATUS_PAGO if pago else STATUS_PENDENTE,
                    )
                )

    def processar_assinaturas(self) -> None:
        df_assin = self.dados["assinaturas"]
        hoje = pd.Timestamp.today().normalize()
        fim_projecao = (hoje + DateOffset(months=6)).to_period("M").to_timestamp()

        for r in df_assin.itertuples():
            ativa = getattr(r, "Ativa", False) is True or str(getattr(r, "Ativa", "")).upper() == "TRUE"
            if not ativa:
                continue

            inicio = r.Inicio
            if pd.isna(inicio):
                continue

            fim_val = getattr(r, "Fim", pd.NaT)
            fim = fim_val if pd.notna(fim_val) else fim_projecao
            if fim < inicio:
                continue

            try:
                datas = pd.date_range(start=inicio, end=fim, freq="MS")
                dia_orig = inicio.day
                datas_ajustadas: list[pd.Timestamp] = []

                for d in datas:
                    try:
                        nova_data = d.replace(day=dia_orig)
                    except ValueError:
                        nova_data = (d + DateOffset(months=1)).replace(day=1) - DateOffset(days=1)
                    if nova_data <= fim:
                        datas_ajustadas.append(nova_data)

                for data_cob in datas_ajustadas:
                    self.lista_movimentacoes.append(
                        Movimentacao(
                            data_original=data_cob,
                            data_competencia=calcular_mes_competencia(data_cob, getattr(r, "Cartao", "")),
                            tipo=TIPO_SAIDA,
                            metodo="Assinatura Recorrente",
                            conta_cartao=getattr(r, "Cartao", ""),
                            categoria=getattr(r, "Categoria", ""),
                            descricao=f"{getattr(r, 'Nome', '')} (Assinatura)",
                            valor=float(getattr(r, "Valor", 0)),
                            status=STATUS_AGUARDANDO_FATURA,
                        )
                    )
            except Exception as error:
                logger.error("Erro ao processar assinatura %s: %s", getattr(r, "Nome", ""), error)

    def processar_debitos(self) -> None:
        df_debito = self.dados["debitos"]
        for r in df_debito.itertuples():
            if pd.isna(r.Data):
                continue
            self.lista_movimentacoes.append(
                Movimentacao(
                    data_original=r.Data,
                    data_competencia=r.Data.to_period("M").to_timestamp(),
                    tipo=TIPO_SAIDA,
                    metodo="Debito/Dinheiro",
                    conta_cartao=getattr(r, "ContaSaida", ""),
                    categoria=getattr(r, "Categoria", ""),
                    descricao=getattr(r, "Descricao", ""),
                    valor=float(getattr(r, "Valor", 0)),
                    status=STATUS_PAGO,
                )
            )

    def processar_receitas(self) -> None:
        df_receitas = self.dados["receitas"]
        for r in df_receitas.itertuples():
            if pd.isna(r.Data):
                continue
            self.lista_movimentacoes.append(
                Movimentacao(
                    data_original=r.Data,
                    data_competencia=r.Data.to_period("M").to_timestamp(),
                    tipo=TIPO_ENTRADA,
                    metodo="Deposito/Salario",
                    conta_cartao=getattr(r, "ContaDestino", ""),
                    categoria=getattr(r, "Categoria", ""),
                    descricao=getattr(r, "Descricao", ""),
                    valor=float(getattr(r, "Valor", 0)),
                    status=STATUS_RECEBIDO,
                )
            )

    def processar_investimentos(self) -> None:
        df_inv = self.dados["investimentos"]

        for r in df_inv.itertuples(index=False):
            if pd.isna(r.Data):
                continue

            operacao = str(r.Operacao).upper().strip()
            valor = float(r.Valor)

            if "APORTE" in operacao:
                self.lista_movimentacoes.append(
                    Movimentacao(
                        data_original=r.Data,
                        data_competencia=r.Data.to_period("M").to_timestamp(),
                        tipo=TIPO_SAIDA,
                        metodo="Investimento",
                        conta_cartao="Conta Corrente",
                        categoria="Investimento",
                        descricao=f"Aporte {r.Tipo}",
                        valor=valor,
                        status=STATUS_PAGO,
                    )
                )
            elif "SAQUE" in operacao or "RESGATE" in operacao or "VENDA" in operacao:
                self.lista_movimentacoes.append(
                    Movimentacao(
                        data_original=r.Data,
                        data_competencia=r.Data.to_period("M").to_timestamp(),
                        tipo=TIPO_ENTRADA,
                        metodo="Resgate Investimento",
                        conta_cartao="Conta Corrente",
                        categoria="Investimento",
                        descricao=f"Resgate {r.Tipo}",
                        valor=valor,
                        status=STATUS_RECEBIDO,
                    )
                )

    def _consolidar_movimentacoes(self) -> pd.DataFrame:
        df_master = pd.DataFrame([m.to_dict() for m in self.lista_movimentacoes])

        if not df_master.empty:
            def validar_pgto(row: pd.Series) -> str:
                if row["Status"] != STATUS_AGUARDANDO_FATURA:
                    return str(row["Status"])
                ultimo_pago = self.mapa_pagamentos.get(row["Conta_Cartao"], pd.NaT)
                if pd.isna(ultimo_pago):
                    return STATUS_PENDENTE
                return STATUS_PAGO if row["DataCompetencia"] <= ultimo_pago else STATUS_PENDENTE

            df_master["Status"] = df_master.apply(validar_pgto, axis=1)
            df_master["ValorFluxo"] = df_master.apply(
                lambda x: x["Valor"] * (-1 if x["Tipo"] == TIPO_SAIDA else 1), axis=1
            )

        return df_master
