"""Renderizacao de resultados SQL como imagem PNG (agnostico de framework).

Extraido da logica do bot do Discord para poder ser reaproveitado pelo bot do
Telegram. Nao importa `discord` nem `telegram`: recebe o retorno de
`executar_sql_livre` e devolve `(texto, png_bytes | None)`, deixando cada bot
decidir como enviar a imagem.
"""

from __future__ import annotations

import io

from utils.logging_config import get_logger

logger = get_logger(__name__)


def _sanitizar_valor(valor, largura_max: int | None = None) -> str:
    """Converte um valor de celula em texto de uma linha, opcionalmente truncado."""
    texto = "NULL" if valor is None else str(valor)
    texto = texto.replace("\n", " ").replace("\r", " ")
    if largura_max is not None and len(texto) > largura_max:
        texto = texto[: largura_max - 1] + "…"
    return texto


def _reordenar_colunas(colunas: list[str]) -> list[str]:
    """Move a coluna 'id' (se existir) para o inicio — chave mais util primeiro."""
    if "id" in colunas:
        return ["id"] + [c for c in colunas if c != "id"]
    return colunas


def _formatar_tabela_ascii(colunas: list[str], linhas: list[dict], largura_max: int = 24) -> str:
    """Tabela ASCII — usada so como fallback caso a renderizacao de imagem falhe."""
    if not linhas:
        return "(0 linhas)"

    larguras = {col: len(str(col)) for col in colunas}
    for linha in linhas:
        for col in colunas:
            larguras[col] = max(larguras[col], len(_sanitizar_valor(linha.get(col), largura_max)))

    cabecalho = " | ".join(str(col).ljust(larguras[col]) for col in colunas)
    separador = "-+-".join("-" * larguras[col] for col in colunas)
    corpo = "\n".join(
        " | ".join(_sanitizar_valor(linha.get(col), largura_max).ljust(larguras[col]) for col in colunas)
        for linha in linhas
    )
    return f"{cabecalho}\n{separador}\n{corpo}"


def renderizar_tabela_png(colunas: list[str], linhas: list[dict]) -> bytes:
    """Renderiza as linhas de um SELECT como imagem PNG (tema escuro estilo Discord)."""
    from PIL import Image, ImageDraw, ImageFont

    def _fonte(tam: int, bold: bool = False):
        candidatos = (
            ["C:/Windows/Fonts/consolab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]
            if bold
            else ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
        )
        for caminho in candidatos:
            try:
                return ImageFont.truetype(caminho, tam)
            except OSError:
                continue
        return ImageFont.load_default(tam)

    fonte = _fonte(20)
    fonte_bold = _fonte(20, bold=True)

    BG, HEADER_BG, ROW_ALT = (30, 31, 34), (43, 45, 49), (35, 36, 40)
    TXT, TXT_HEAD, ACCENT, GRID = (219, 222, 225), (255, 255, 255), (88, 101, 242), (55, 57, 62)
    PAD_X, PAD_Y, MARGEM = 14, 10, 16

    medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def _largura(txt: str, ft) -> int:
        return medidor.textbbox((0, 0), txt, font=ft)[2]

    larguras = {}
    for col in colunas:
        w = _largura(str(col), fonte_bold)
        for linha in linhas:
            w = max(w, _largura(_sanitizar_valor(linha.get(col)), fonte))
        larguras[col] = w + PAD_X * 2

    alt_linha = fonte.getbbox("Ag")[3] + PAD_Y * 2
    larg_total = sum(larguras.values())
    alt_total = alt_linha * (len(linhas) + 1)

    img = Image.new("RGB", (larg_total + MARGEM * 2, alt_total + MARGEM * 2), BG)
    d = ImageDraw.Draw(img)
    x0, y0 = MARGEM, MARGEM

    # Cabecalho + linha de destaque
    d.rectangle([x0, y0, x0 + larg_total, y0 + alt_linha], fill=HEADER_BG)
    cx = x0
    for col in colunas:
        d.text((cx + PAD_X, y0 + PAD_Y), str(col), font=fonte_bold, fill=TXT_HEAD)
        cx += larguras[col]
    d.rectangle([x0, y0 + alt_linha - 2, x0 + larg_total, y0 + alt_linha], fill=ACCENT)

    # Linhas (com zebra e 'id' destacado)
    for i, linha in enumerate(linhas):
        ry = y0 + alt_linha * (i + 1)
        if i % 2 == 1:
            d.rectangle([x0, ry, x0 + larg_total, ry + alt_linha], fill=ROW_ALT)
        cx = x0
        for col in colunas:
            eh_id = col == "id"
            d.text(
                (cx + PAD_X, ry + PAD_Y),
                _sanitizar_valor(linha.get(col)),
                font=fonte_bold if eh_id else fonte,
                fill=ACCENT if eh_id else TXT,
            )
            cx += larguras[col]

    # Grade vertical sutil entre colunas
    cx = x0
    for col in colunas[:-1]:
        cx += larguras[col]
        d.line([cx, y0, cx, y0 + alt_total], fill=GRID, width=1)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def montar_resposta_sql(resultado: dict, limite: int = 20) -> tuple[str, bytes | None]:
    """Transforma o retorno de `executar_sql_livre` em (texto, png_bytes | None).

    - Erro: ("❌ ...", None)
    - INSERT/UPDATE/DELETE/DDL: ("✅ Executado ...", None)
    - SELECT: (rodape, png_bytes) — ou (texto ASCII, None) se a imagem falhar.
    """
    if not resultado["ok"]:
        return f"❌ Erro ao executar a query:\n<pre>{resultado['erro'][:1800]}</pre>", None

    if resultado["tipo"] == "exec":
        return f"✅ Executado com sucesso. Linhas afetadas: <b>{resultado['rowcount']}</b>", None

    colunas = _reordenar_colunas(resultado["colunas"])
    linhas = resultado["linhas"]
    total = len(linhas)
    exibidas = linhas[: max(1, limite)]

    if not exibidas:
        return "📊 0 linha(s).", None

    rodape = f"📊 {total} linha(s)"
    if total > len(exibidas):
        rodape += f" — exibindo as primeiras {len(exibidas)}"

    # Resultado sempre como imagem; se a renderizacao falhar, cai para texto.
    try:
        return rodape, renderizar_tabela_png(colunas, exibidas)
    except Exception as e:  # noqa: BLE001
        logger.warning("Falha ao renderizar imagem do /sql, usando texto: %s", e)
        tabela = _formatar_tabela_ascii(colunas, exibidas)
        return f"<pre>{tabela}</pre>\n\n{rodape}", None
