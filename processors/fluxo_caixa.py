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
from utils import calcular_mes_competencia, get_logger, normalizar_nome_cartao

logger = get_logger(__name__)

# Periodicidade das assinaturas -> intervalo em meses entre duas cobrancas.
# A chave e comparada em caixa alta; ausente ou desconhecida vira mensal.
MESES_POR_PERIODICIDADE = {"MENSAL": 1, "ANUAL": 12}

# Ate onde projetar assinaturas sem data de Fim. A anual precisa de mais de 12
# meses para que sempre caia exatamente uma cobranca dentro da janela.
MESES_PROJECAO_MENSAL = 3
MESES_PROJECAO_ANUAL = 13


class FluxoCaixaProcessor:
    def __init__(self, dados: dict[str, Any], mapa_pagamentos: dict[str, pd.Timestamp]):
        self.dados = dados
        self.mapa_pagamentos = mapa_pagamentos
        self.lista_movimentacoes: list[Movimentacao] = []

    @staticmethod
    def _normalizar_data_hora(valor: Any) -> pd.Timestamp:
        if pd.isna(valor):
            return pd.NaT
        if isinstance(valor, pd.Timestamp):
            return valor
        if isinstance(valor, str):
            return pd.to_datetime(valor, dayfirst=True, errors="coerce")
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(valor, unit="D")
        return pd.to_datetime(valor, dayfirst=True, errors="coerce")

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
            cartao = normalizar_nome_cartao(getattr(r, "Cartao", ""))
            primeira_fat = calcular_mes_competencia(data, cartao)
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
                        conta_cartao=cartao,
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

    @staticmethod
    def _intervalo_assinatura(periodicidade: Any) -> int:
        """Traduz a periodicidade da assinatura para um intervalo em meses.

        Valor ausente ou desconhecido cai em mensal, que era o unico
        comportamento possivel antes da coluna existir.
        """
        chave = str(periodicidade or "").strip().upper()
        return MESES_POR_PERIODICIDADE.get(chave, 1)

    @staticmethod
    def _dia_cobranca(registro: Any, inicio: pd.Timestamp) -> int:
        """Dia do mes em que a assinatura e cobrada, com fallback para o Inicio."""
        dia = getattr(registro, "DiaCobranca", None)
        try:
            if dia is not None and pd.notna(dia) and str(dia).strip() != "":
                return min(31, max(1, int(float(dia))))
        except (TypeError, ValueError):
            pass
        return inicio.day

    @staticmethod
    def _ajustar_dia(referencia: pd.Timestamp, dia: int) -> pd.Timestamp:
        """Aplica o dia de cobranca, recuando para o ultimo dia em meses curtos."""
        try:
            return referencia.replace(day=dia)
        except ValueError:
            return (referencia + DateOffset(months=1)).replace(day=1) - DateOffset(days=1)

    def processar_assinaturas(self) -> None:
        df_assin = self.dados["assinaturas"]
        hoje = pd.Timestamp.today().normalize()

        for r in df_assin.itertuples():
            ativa = getattr(r, "Ativa", False) is True or str(getattr(r, "Ativa", "")).upper() == "TRUE"
            if not ativa:
                continue

            inicio = r.Inicio
            if pd.isna(inicio):
                continue

            intervalo = self._intervalo_assinatura(getattr(r, "Periodicidade", ""))

            # A anual precisa de uma janela maior que a mensal, senao quase nunca
            # cairia dentro da projecao. O fim e o ultimo dia do mes-limite, para
            # nao descartar cobrancas com dia > 1.
            meses_projecao = MESES_PROJECAO_ANUAL if intervalo >= 12 else MESES_PROJECAO_MENSAL
            fim_projecao = hoje + DateOffset(months=meses_projecao, day=31)

            fim_val = getattr(r, "Fim", pd.NaT)
            fim = fim_val if pd.notna(fim_val) else fim_projecao
            if fim < inicio:
                continue

            try:
                dia_cobranca = self._dia_cobranca(r, inicio)
                cartao = normalizar_nome_cartao(getattr(r, "Cartao", ""))
                sufixo = "Assinatura Anual" if intervalo >= 12 else "Assinatura"

                # Avanca a partir do proprio Inicio (e nao do inicio do mes), o que
                # preserva o mes de aniversario das anuais e nao perde a primeira
                # cobranca das mensais.
                # A tolerancia de um intervalo evita perder a ultima cobranca
                # quando DiaCobranca e anterior ao dia do Inicio (ex.: Inicio em
                # 15/01 cobrando todo dia 5 -> referencia 15/04 passa de um fim
                # em 05/04, mas a cobranca de 05/04 ainda vale).
                limite_varredura = fim + DateOffset(months=intervalo)
                ocorrencia = 0
                while True:
                    referencia = inicio + DateOffset(months=intervalo * ocorrencia)
                    if referencia > limite_varredura:
                        break

                    data_cob = self._ajustar_dia(referencia, dia_cobranca)
                    ocorrencia += 1

                    if data_cob < inicio or data_cob > fim:
                        continue

                    self.lista_movimentacoes.append(
                        Movimentacao(
                            data_original=data_cob,
                            data_competencia=calcular_mes_competencia(data_cob, cartao),
                            tipo=TIPO_SAIDA,
                            metodo="Assinatura Recorrente",
                            conta_cartao=cartao,
                            categoria=getattr(r, "Categoria", ""),
                            descricao=f"{getattr(r, 'Nome', '')} ({sufixo})",
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
            data_hora = self._normalizar_data_hora(getattr(r, "DataHora", pd.NaT))
            if pd.isna(data_hora):
                continue

            operacao = str(r.Operacao).upper().strip()
            valor = float(r.Valor)

            if "APORTE" in operacao:
                self.lista_movimentacoes.append(
                    Movimentacao(
                        data_original=data_hora,
                        data_competencia=data_hora.to_period("M").to_timestamp(),
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
                        data_original=data_hora,
                        data_competencia=data_hora.to_period("M").to_timestamp(),
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
                conta_cartao = normalizar_nome_cartao(row["Conta_Cartao"])
                ultimo_pago = self.mapa_pagamentos.get(conta_cartao, pd.NaT)
                if pd.isna(ultimo_pago):
                    return STATUS_PENDENTE
                return STATUS_PAGO if row["DataCompetencia"] <= ultimo_pago else STATUS_PENDENTE

            df_master["Status"] = df_master.apply(validar_pgto, axis=1)
            df_master["ValorFluxo"] = df_master.apply(
                lambda x: x["Valor"] * (-1 if x["Tipo"] == TIPO_SAIDA else 1), axis=1
            )

        return df_master
