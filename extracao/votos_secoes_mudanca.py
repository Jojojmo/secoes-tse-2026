"""
Agrega os votos para Presidente (1º turno) por seção, só para as seções que
mudaram entre o 1º e o 2º turno.

Entradas (do freeze mais recente, ou do informado em --freeze):
  dados/geral/votos_presidente_por_secao_2026.csv     (gerado por votos_primeiro_turno.py, ~1 GB;
                                                      estático, fica fora dos freezes)
  saida/<freeze>/secoes_mudanca_local_1t_2t.csv        (gerado por secoes_tse_2026.py)

Uso:
    uv run extracao/votos_secoes_mudanca.py [--freeze 2026-10-19_1000]
    uv run extracao/votos_secoes_mudanca.py [--freeze <nome>] <votos.csv> <secoes_mudanca.csv>

Saída: saida/<freeze>/votos_secoes_mudanca_1t.csv — uma linha por seção, uma coluna por
candidato (inclusive VOTO BRANCO e VOTO NULO) e TOTAL_VOTOS.

O CSV de votos é lido em blocos e só com as colunas necessárias; cada bloco é
filtrado pelas seções de interesse antes de agregar, então a memória fica
limitada ao tamanho do bloco.
"""
import sys

import pandas as pd

import freeze

VOTOS = "votos_presidente_por_secao_2026.csv"
MUDANCA = "secoes_mudanca_local_1t_2t.csv"

CHAVE = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
# contexto da mudança copiado para a saída: local, endereço e coordenadas dos dois turnos
CONTEXTO = ["NM_MUNICIPIO"] + [
    f"{c}_{t}" for t in ("1T", "2T")
    for c in ("NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO", "NM_BAIRRO",
              "NR_LATITUDE", "NR_LONGITUDE")
] + ["MOTIVO"]
COORDENADAS = [c for c in CONTEXTO if c.startswith(("NR_LATITUDE", "NR_LONGITUDE"))]
BRANCO_NULO = {"95", "96"}
TAMANHO_BLOCO = 500_000


def normalizar(df):
    # o arquivo de votos traz CD_MUNICIPIO sem zeros à esquerda (86363 / 1015) e o
    # do eleitorado com zeros (01015): compara tudo como inteiro
    df = df.copy()
    for c in CHAVE[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def main(votos, mudanca, nome_freeze):
    sys.stdout.reconfigure(encoding="utf-8")
    SAIDA = freeze.SAIDA / nome_freeze / "votos_secoes_mudanca_1t.csv"
    print(f"Freeze {nome_freeze}")

    secoes = normalizar(pd.read_csv(mudanca, sep=";", encoding="utf-8-sig", dtype=str))
    secoes = secoes[CHAVE + [c for c in CONTEXTO if c in secoes.columns]].drop_duplicates(CHAVE)
    # o TSE grava as coordenadas com vírgula decimal ("-30,0592147")
    for c in COORDENADAS:
        if c in secoes.columns:
            secoes[c] = pd.to_numeric(secoes[c].str.replace(",", "."), errors="coerce")
    indice = pd.MultiIndex.from_frame(secoes[CHAVE])
    print(f"Seções que mudaram entre turnos: {len(secoes):,}")

    partes = []
    lidas = 0
    leitor = pd.read_csv(
        votos, sep=";", encoding="utf-8-sig", dtype=str, chunksize=TAMANHO_BLOCO,
        usecols=CHAVE + ["NR_TURNO", "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS"],
    )
    for bloco in leitor:
        lidas += len(bloco)
        bloco = bloco[bloco["NR_TURNO"] == "1"]
        bloco = normalizar(bloco)
        bloco = bloco[pd.MultiIndex.from_frame(bloco[CHAVE]).isin(indice)]
        if bloco.empty:
            continue
        bloco["QT_VOTOS"] = pd.to_numeric(bloco["QT_VOTOS"]).astype("int64")
        partes.append(bloco.groupby(CHAVE + ["NR_VOTAVEL", "NM_VOTAVEL"])["QT_VOTOS"].sum())
        print(f"  {lidas:,} linhas lidas", end="\r")
    print(f"  {lidas:,} linhas lidas")

    if not partes:
        sys.exit("Nenhum voto encontrado para as seções que mudaram.")

    # a mesma seção pode aparecer em mais de um bloco: soma de novo
    longo = pd.concat(partes).groupby(level=list(range(len(CHAVE) + 2))).sum().reset_index()

    # candidatos em ordem de número, com branco e nulo no fim
    nomes = (longo[["NR_VOTAVEL", "NM_VOTAVEL"]].drop_duplicates("NR_VOTAVEL")
             .assign(_bn=lambda d: d["NR_VOTAVEL"].isin(BRANCO_NULO),
                     _nr=lambda d: d["NR_VOTAVEL"].astype(int))
             .sort_values(["_bn", "_nr"]))
    colunas = [f"{nr} - {nm}" for nr, nm in zip(nomes["NR_VOTAVEL"], nomes["NM_VOTAVEL"])]
    longo["CANDIDATO"] = longo["NR_VOTAVEL"] + " - " + longo["NM_VOTAVEL"]

    largo = (longo.pivot_table(index=CHAVE, columns="CANDIDATO", values="QT_VOTOS",
                               aggfunc="sum", fill_value=0)
             .reindex(columns=colunas, fill_value=0))
    largo.columns.name = None
    largo["TOTAL_VOTOS"] = largo.sum(axis=1)

    saida = secoes.merge(largo.reset_index(), on=CHAVE, how="inner").sort_values(CHAVE)
    saida["CD_MUNICIPIO"] = saida["CD_MUNICIPIO"].astype(str).str.zfill(5)
    saida.to_csv(SAIDA, sep=";", index=False, encoding="utf-8-sig")

    sem_votos = len(secoes) - len(saida)
    print(f"Seções com votos: {len(saida):,}")
    print(f"Seções sem votos no arquivo (ex.: agregadas, cujos votos vão na principal): {sem_votos:,}")
    print("\nTotal por candidato nessas seções:")
    print(saida[colunas + ["TOTAL_VOTOS"]].sum().to_string())
    print(f"\nArquivo gravado: {SAIDA}")


if __name__ == "__main__":
    nome, args = freeze.escolher(sys.argv[1:])
    if len(args) not in (0, 2):
        sys.exit(__doc__)
    args = args or [freeze.GERAL / VOTOS, freeze.SAIDA / nome / MUDANCA]
    main(*args, nome)
