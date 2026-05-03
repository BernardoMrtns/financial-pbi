import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.getcwd())

from config import SCHEMA_ABAS
from datetime import datetime


def parse_date(value: str, preservar_hora: bool):
    formats = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            if preservar_hora:
                return dt
            return dt.replace(hour=0, minute=0, second=0)
        except Exception:
            continue
    # fallback: try ISO parse
    try:
        dt = datetime.fromisoformat(value)
        if preservar_hora:
            return dt
        return dt.replace(hour=0, minute=0, second=0)
    except Exception:
        return None


def format_date(dt: datetime, name: str):
    if dt is None:
        return ""
    if name in {"InvestimentoBTC", "InvestimentoCripto", "InvestimentoCDI", "Investimentos"}:
        return dt.strftime("%d/%m/%Y %H:%M:%S")
    return dt.strftime("%d/%m/%Y")


def parse_number(val: str):
    if val is None:
        return ""
    s = str(val).strip()
    if s == "":
        return ""
    # Handle common formats:
    # - If both '.' and ',' present, assume '.' thousands and ',' decimal -> remove dots, replace comma
    # - If only ',' present -> replace with '.'
    # - Otherwise keep as is
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        f = float(s)
        return f
    except Exception:
        return ""


def preview_for_sheet(name: str, rows: list[list], columns: list[str]):
    print(f"--- Preview for {name} ---")
    out_rows = []
    for r in rows:
        row_out = []
        for col_name, val in zip(columns, r):
            if col_name == "Data":
                preservar = name == "Investimentos"
                dt = parse_date(str(val), preservar)
                row_out.append(format_date(dt, name))
            elif any(k in col_name for k in ["Valor", "ValorTotal", "ValorEntrada"]):
                num = parse_number(str(val))
                if num == "":
                    row_out.append("")
                else:
                    row_out.append(f"{num:.2f}")
            elif col_name in {"Parcelas", "QtdPagas"}:
                try:
                    row_out.append(str(int(float(val))))
                except Exception:
                    row_out.append("0")
            else:
                row_out.append(str(val))
        out_rows.append(row_out)

    # Print rows
    for orow in out_rows:
        print("\t".join(orow))
    print()


if __name__ == "__main__":
    print("Note: running local preview (no Google Sheets connection).")

    # Samples based on user's examples
    receitas_rows = [
        ["01/05/2026", "Salário", "Trabalho", "2369.67", "Inter"],
        ["01/05/2026", "Passagem Malu", "Pix", "22.08", "Inter"],
        ["04/05/2026", "Virginia", "Trabalho", "200.00", "Nubank"],
        ["04/05/2026", "Gasolina UFOP", "Pix", "49.61", "Nubank"],
    ]

    debito_rows = [
        ["01/05/2026", "Lambe Lambe", "Comida", "55.00", "Inter"],
        ["02/05/2026", "Bala Azeda", "Comida", "33.00", "Inter"],
        ["03/05/2026", "Energetico e CocaZero", "Comida", "16.19", "Inter"],
    ]

    compras_rows = [
        ["09/04/2026", "Ingresso Spring + Hiper", "Lazer", "Nubank", "46.01", "1"],
        ["10/04/2026", "Hiper 08.04", "Comida", "Nubank", "12.27", "1"],
        ["10/04/2026", "Hiper 10.04", "Comida", "Nubank", "21.46", "1"],
        ["11/04/2026", "Lanchonete UFOP 11.04", "Comida", "Nubank", "8.00", "1"],
    ]

    pix_rows = [
        ["09/11/2025", "Adesivos, DongleBT, Case, CP2077", "Eletrônicos", "147.38", "36.86", "4"],
        ["28/11/2025", "Scryrox V6, Scyrox SOSU, Feets", "Eletrônicos", "637.99", "187.99", "4"],
        ["02/12/2025", "Switches Gateron V3 Pro Yellow", "Eletrônicos", "90.34", "22.60", "4"],
    ]

    invest_rows = [
        ["12/03/2026 00:00:00", "CDI", "Saque", "1581.84", "0.00000000", ""],
        ["24/02/2026 09:12:00", "BTC", "Aporte", "600.00", "0.00137169", ""],
        ["18/03/2026 18:30:00", "SOL", "Aporte", "1450.00", "2.99006200", ""],
        ["05/04/2026 00:00:00", "CDI", "Aporte", "1467.40", "0.00000000", ""],
    ]

    preview_for_sheet("Receitas", receitas_rows, SCHEMA_ABAS["Receitas"])
    preview_for_sheet("DebitoAvulso", debito_rows, SCHEMA_ABAS["DebitoAvulso"])
    preview_for_sheet("ComprasCartao", compras_rows, SCHEMA_ABAS["ComprasCartao"])
    preview_for_sheet("PixParcelado", pix_rows, SCHEMA_ABAS["PixParcelado"])
    preview_for_sheet("Investimentos", invest_rows, SCHEMA_ABAS["Investimentos"])
