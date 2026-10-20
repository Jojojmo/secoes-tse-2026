# Baixa os votos por seção (1º turno, Presidente) para dados/geral/. O resultado do
# 1º turno não muda mais, então o arquivo fica fora dos freezes.
from zipfile import ZipFile
import requests
import pandas as pd

import freeze

URL = (
    "https://cdn.tse.jus.br/estatistica/sead/"
    "odsele/votacao_secao/votacao_secao_2026_BR.zip"
)

PASTA = freeze.GERAL
PASTA.mkdir(parents=True, exist_ok=True)

ARQUIVO_ZIP = PASTA / "votacao_secao_2026_BR.zip"
ARQUIVO_SAIDA = PASTA / "votos_presidente_por_secao_2026.csv"

# 1. Download do arquivo oficial
with requests.get(URL, stream=True, timeout=120) as response:
    response.raise_for_status()

    with ARQUIVO_ZIP.open("wb") as arquivo:
        for bloco in response.iter_content(chunk_size=1024 * 1024):
            if bloco:
                arquivo.write(bloco)

# 2. Identifica o CSV dentro do ZIP
with ZipFile(ARQUIVO_ZIP) as zip_file:
    arquivos_csv = [
        nome for nome in zip_file.namelist()
        if nome.lower().endswith(".csv")
    ]

    if not arquivos_csv:
        raise RuntimeError("Nenhum CSV encontrado no ZIP.")

    nome_csv = arquivos_csv[0]

    # 3. Lê em blocos e filtra os votos presidenciais
    primeira_escrita = True

    with zip_file.open(nome_csv) as arquivo:
        for bloco in pd.read_csv(
            arquivo,
            sep=";",
            encoding="latin1",
            dtype=str,
            chunksize=200_000,
        ):
            bloco.columns = bloco.columns.str.strip()

            filtro = (
                bloco["DS_CARGO"].str.contains(
                    "PRESIDENTE", case=False, na=False
                )
                & bloco["NR_TURNO"].eq("1")
            )

            resultado = bloco.loc[filtro].copy()

            if resultado.empty:
                continue

            resultado.to_csv(
                ARQUIVO_SAIDA,
                sep=";",
                index=False,
                mode="w" if primeira_escrita else "a",
                header=primeira_escrita,
                encoding="utf-8-sig",
            )

            primeira_escrita = False

if primeira_escrita:
    raise RuntimeError(
        "Nenhum voto encontrado. Confira os nomes das colunas "
        "e os valores de cargo e turno do arquivo."
    )

print(f"Arquivo gerado: {ARQUIVO_SAIDA.resolve()}")
