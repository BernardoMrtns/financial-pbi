"""
Módulo para processamento de movimentações financeiras
"""
import pandas as pd
from pandas.tseries.offsets import DateOffset
from modules.utils import calcular_mes_competencia


class FluxoCaixaProcessor:
    """
    Responsável por processar todas as movimentações financeiras
    e gerar o fluxo de caixa consolidado
    """

    def __init__(self, dados, mapa_pagamentos):
        self.dados = dados
        self.mapa_pagamentos = mapa_pagamentos
        self.lista_movimentacoes = []

    def processar_todas_movimentacoes(self):
        """
        Processa todas as fontes de movimentação e retorna DataFrame consolidado
        """
        print("💰 Processando fluxo de caixa...")

        self.processar_cartao()
        self.processar_pix_parcelado()
        self.processar_assinaturas()
        self.processar_debitos()
        self.processar_receitas()
        self.processar_investimentos()

        return self._consolidar_movimentacoes()

    def processar_cartao(self):
        """
        Processa compras no cartão de crédito
        """
        df_compras = self.dados['compras']

        for r in df_compras.itertuples():
            data = r.Data
            if pd.isna(data): 
                continue

            total = r.ValorTotal
            n_parc = int(r.Parcelas) if pd.notna(r.Parcelas) and r.Parcelas != "" else 1
            primeira_fat = calcular_mes_competencia(data, getattr(r, 'Cartao', ''))

            if pd.isna(primeira_fat): 
                continue

            valor_base = round(total / n_parc, 2)
            valores = [valor_base] * n_parc
            valores[-1] = round(total - sum(valores[:-1]), 2)

            for i in range(n_parc):
                mes_ref = (primeira_fat + DateOffset(months=i)).to_period("M").to_timestamp()
                self.lista_movimentacoes.append({
                    "DataOriginal": data, 
                    "DataCompetencia": mes_ref, 
                    "Tipo": "Saída", 
                    "Metodo": "Cartão de Crédito",
                    "Conta_Cartao": getattr(r, 'Cartao', ''), 
                    "Categoria": getattr(r, 'Categoria', ''), 
                    "Descricao": f"{getattr(r, 'Descricao', '')} ({i+1}/{n_parc})",
                    "Valor": valores[i], 
                    "Status": "Aguardando Fatura"
                })

    def processar_pix_parcelado(self):
        """
        Processa pagamentos PIX parcelados
        """
        df_pix = self.dados['pix']
        df_pix["QtdPagas"] = pd.to_numeric(df_pix["QtdPagas"], errors="coerce").fillna(0).astype(int)
        df_pix["ValorEntrada"] = pd.to_numeric(df_pix["ValorEntrada"], errors="coerce").fillna(df_pix["ValorTotal"]/4)

        for r in df_pix.itertuples():
            data = r.Data
            if pd.isna(data): 
                continue

            total = r.ValorTotal
            entrada = r.ValorEntrada
            qtd_pagas = r.QtdPagas
            saldo = total - entrada
            valores = [entrada, round(saldo/3, 2), round(saldo/3, 2), round(total - (entrada + 2*round(saldo/3, 2)), 2)]

            for i in range(4):
                num = i + 1
                vencimento = data + pd.DateOffset(days=15 * i)
                mes_ref = vencimento.to_period("M").to_timestamp()
                pago = (num <= qtd_pagas) or (vencimento <= pd.Timestamp.now())

                self.lista_movimentacoes.append({
                    "DataOriginal": data, 
                    "DataCompetencia": mes_ref, 
                    "Tipo": "Saída", 
                    "Metodo": "Pix Parcelado",
                    "Conta_Cartao": "Conta Corrente", 
                    "Categoria": getattr(r, 'Categoria', ''), 
                    "Descricao": f"{getattr(r, 'Descricao', '')} ({num}/4)",
                    "Valor": valores[i], 
                    "Status": "Pago" if pago else "Pendente"
                })

    def processar_assinaturas(self):
        """
        Processa assinaturas recorrentes
        """
        df_assin = self.dados['assinaturas']
        hoje = pd.Timestamp.today().normalize()
        fim_projecao = (hoje + DateOffset(months=6)).to_period("M").to_timestamp()

        for r in df_assin.itertuples():
            ativa = getattr(r, 'Ativa', False) == True or str(getattr(r, 'Ativa', '')).upper() == "TRUE"
            if not ativa: 
                continue

            inicio = r.Inicio
            if pd.isna(inicio): 
                continue

            fim_val = getattr(r, 'Fim', pd.NaT)
            fim = fim_val if pd.notna(fim_val) else fim_projecao
            if fim < inicio: 
                continue

            try:
                datas = pd.date_range(start=inicio, end=fim, freq='MS')
                dia_orig = inicio.day
                datas_ajustadas = []

                for d in datas:
                    try:
                        nova_data = d.replace(day=dia_orig)
                    except ValueError:
                        nova_data = (d + DateOffset(months=1)).replace(day=1) - DateOffset(days=1)
                    if nova_data <= fim:
                        datas_ajustadas.append(nova_data)

                for data_cob in datas_ajustadas:
                    self.lista_movimentacoes.append({
                        "DataOriginal": data_cob, 
                        "DataCompetencia": calcular_mes_competencia(data_cob, getattr(r, 'Cartao', '')), 
                        "Tipo": "Saída",
                        "Metodo": "Assinatura Recorrente", 
                        "Conta_Cartao": getattr(r, 'Cartao', ''), 
                        "Categoria": getattr(r, 'Categoria', ''),
                        "Descricao": f"{getattr(r, 'Nome', '')} (Assinatura)", 
                        "Valor": float(getattr(r, 'Valor', 0)), 
                        "Status": "Aguardando Fatura"
                    })
            except Exception as e:
                print(f"Erro ao processar assinatura {getattr(r, 'Nome', '')}: {e}")

    def processar_debitos(self):
        """
        Processa débitos avulsos
        """
        df_debito = self.dados['debitos']

        for r in df_debito.itertuples():
            if pd.isna(r.Data): 
                continue
            self.lista_movimentacoes.append({
                "DataOriginal": r.Data, 
                "DataCompetencia": r.Data.to_period("M").to_timestamp(), 
                "Tipo": "Saída",
                "Metodo": "Débito/Dinheiro", 
                "Conta_Cartao": getattr(r, 'ContaSaida', ''), 
                "Categoria": getattr(r, 'Categoria', ''),
                "Descricao": getattr(r, 'Descricao', ''), 
                "Valor": float(getattr(r, 'Valor', 0)), 
                "Status": "Pago"
            })

    def processar_receitas(self):
        """
        Processa receitas/entradas
        """
        df_receitas = self.dados['receitas']

        for r in df_receitas.itertuples():
            if pd.isna(r.Data): 
                continue
            self.lista_movimentacoes.append({
                "DataOriginal": r.Data, 
                "DataCompetencia": r.Data.to_period("M").to_timestamp(), 
                "Tipo": "Entrada",
                "Metodo": "Depósito/Salário", 
                "Conta_Cartao": getattr(r, 'ContaDestino', ''), 
                "Categoria": getattr(r, 'Categoria', ''),
                "Descricao": getattr(r, 'Descricao', ''), 
                "Valor": float(getattr(r, 'Valor', 0)), 
                "Status": "Recebido"
            })

    def processar_investimentos(self):
        """
        Processa movimentações de investimentos
        """
        df_inv = self.dados['investimentos']

        for _, r in df_inv.iterrows():
            if pd.isna(r["Data"]): 
                continue

            operacao = str(r["Operacao"]).upper().strip()
            valor = float(r["Valor"])

            if "APORTE" in operacao:
                self.lista_movimentacoes.append({
                    "DataOriginal": r["Data"], 
                    "DataCompetencia": r["Data"].to_period("M").to_timestamp(),
                    "Tipo": "Saída", 
                    "Metodo": "Investimento", 
                    "Conta_Cartao": "Conta Corrente",
                    "Categoria": "Investimento", 
                    "Descricao": f"Aporte {r['Tipo']}",
                    "Valor": valor, 
                    "Status": "Pago"
                })
            elif "SAQUE" in operacao or "RESGATE" in operacao or "VENDA" in operacao:
                self.lista_movimentacoes.append({
                    "DataOriginal": r["Data"], 
                    "DataCompetencia": r["Data"].to_period("M").to_timestamp(),
                    "Tipo": "Entrada", 
                    "Metodo": "Resgate Investimento", 
                    "Conta_Cartao": "Conta Corrente",
                    "Categoria": "Investimento", 
                    "Descricao": f"Resgate {r['Tipo']}",
                    "Valor": valor, 
                    "Status": "Recebido"
                })

    def _consolidar_movimentacoes(self):
        """
        Consolida todas as movimentações em um DataFrame único
        """
        df_master = pd.DataFrame(self.lista_movimentacoes)

        if not df_master.empty:
            def validar_pgto(row):
                if row["Status"] != "Aguardando Fatura": 
                    return row["Status"]
                ultimo_pago = self.mapa_pagamentos.get(row["Conta_Cartao"], pd.NaT)
                if pd.isna(ultimo_pago): 
                    return "Pendente"
                return "Pago" if row["DataCompetencia"] <= ultimo_pago else "Pendente"

            df_master["Status"] = df_master.apply(validar_pgto, axis=1)
            df_master["ValorFluxo"] = df_master.apply(
                lambda x: x["Valor"] * (-1 if x["Tipo"] == "Saída" else 1), axis=1
            )

        return df_master