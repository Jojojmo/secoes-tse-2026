"""
Gera, para um freeze (ver freeze.py):
  1) seções agregadas no 1º turno, a partir do eleitorado_local_votacao_2026 (dados/geral/)
  2) seções que mudaram de local entre o 1º e o 2º turno, a partir da lista oficial
     do TSE salva no freeze (secoes_eleitorais_alteradas_2t-pais_2026, o .csv.zip dos
     Dados Abertos ou o .csv da página Capilaridade),
     completada com o eleitorado: código do município, nº, endereço e coordenadas
     do local nos dois turnos

Uso:
    uv run extracao/secoes_tse_2026.py                       # freeze mais recente
    uv run extracao/secoes_tse_2026.py --freeze 2026-10-19_1708
    uv run extracao/secoes_tse_2026.py [--freeze <nome>] outro_eleitorado.zip|.csv

Saídas em saida/<freeze>/: os dois CSVs de detalhe e resumo.json (totais por UF e município).
Ao fim, saida/freezes.csv é reescrito.

Layout conforme o LEIAME do TSE: Latin-1, ';' como separador, campos entre aspas,
#NULO / -1 = em branco, #NE / -3 = não registrado.
"""
import io
import json
import sys
import zipfile
from datetime import datetime

import pandas as pd

import freeze

ELEITORADO = freeze.GERAL / "eleitorado_local_votacao_2026.zip"

CHAVE = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
LOCAL = ["NR_LOCAL_VOTACAO", "NM_LOCAL_VOTACAO", "DS_ENDERECO", "NM_BAIRRO", "NR_CEP",
         "NR_LATITUDE", "NR_LONGITUDE"]
TIPO = ["CD_TIPO_SECAO_AGREGADA", "DS_TIPO_SECAO_AGREGADA", "NR_SECAO_PRINCIPAL"]

# Nulos (#NULO / -1 = em branco) e não registrados (#NE / -3), além de campos vazios
NULOS = ["#NULO", "#NE", "-1", "-3"]


def ler(caminho):
    opts = dict(sep=";", encoding="latin-1", dtype=str, na_values=NULOS)
    if caminho.lower().endswith(".zip"):
        with zipfile.ZipFile(caminho) as z:
            csvs = [n for n in z.namelist() if n.lower().endswith(".csv")]
            # O zip traz o arquivo _BRASIL (todas as UFs) e um CSV por UF:
            # usa só o BRASIL quando existir, senão concatena os das UFs
            brasil = [n for n in csvs if n.upper().endswith("_BRASIL.CSV")]
            csvs = brasil or csvs
            df = pd.concat((pd.read_csv(z.open(n), **opts) for n in csvs), ignore_index=True)
    else:
        df = pd.read_csv(caminho, **opts)
    return df.drop_duplicates()


def ler_alteradas(pasta):
    """Lista oficial de seções alteradas no 2º turno, no zip dos Dados Abertos ou no CSV
    da página Capilaridade. Devolve também a data/hora em que o TSE gerou o arquivo,
    que só o zip informa (data do CSV dentro dele); para o CSV solto fica vazia."""
    caminho = freeze.lista_alteradas(pasta)
    if caminho is None:
        sys.exit(f"Nenhuma lista de seções alteradas em {pasta} ({freeze.ALTERADAS}*.zip ou *.csv).")
    gerada = ""
    if caminho.suffix.lower() == ".zip":
        with zipfile.ZipFile(caminho) as z:
            info = next(i for i in z.infolist() if i.filename.lower().endswith(".csv"))
            bruto = z.read(info)
        gerada = datetime(*info.date_time).strftime("%d/%m/%Y %H:%M:%S")
    else:
        bruto = caminho.read_bytes()
    # o zip vem em Latin-1; o CSV da Capilaridade pode vir em UTF-8 e com outro separador
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    df.columns = df.columns.str.strip().str.upper()
    return df.drop_duplicates(), gerada, caminho.name


def nome_local(s):
    """Nome de local comparável: a lista oficial troca '.' por ',' ("E, M, JOAO GOULART")."""
    s = s.fillna("").str.upper().str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii")
    return s.str.replace(r"[.,\-]", " ", regex=True).str.split().str.join(" ")


def registro_agregada(r):
    """Uma seção agregada no schema comum dos JSON por UF."""
    def txt(v):
        return None if pd.isna(v) else v

    def num(v, tipo=int):
        # coordenadas do TSE vêm com vírgula decimal ("-30,0592147")
        try:
            return None if pd.isna(v) else tipo(str(v).replace(",", "."))
        except ValueError:
            return None

    return {
        "uf": r["SG_UF"],
        "cd_municipio": r["CD_MUNICIPIO"],
        "municipio": r["NM_MUNICIPIO"],
        "zona": num(r["NR_ZONA"]),
        "secao": num(r["NR_SECAO"]),
        "secao_principal": num(r["NR_SECAO_PRINCIPAL"]),
        "nr_local": num(r["NR_LOCAL_VOTACAO"]),
        "local": txt(r["NM_LOCAL_VOTACAO"]),
        "endereco": txt(r["DS_ENDERECO"]),
        "bairro": txt(r["NM_BAIRRO"]),
        "cep": txt(r["NR_CEP"]),
        "lat": num(r["NR_LATITUDE"], float),
        "lon": num(r["NR_LONGITUDE"], float),
        "eleitores": num(r["QT_ELEITOR_SECAO"]),
    }


def mudancas_oficiais(alt, t1, t2, df):
    """Completa a lista oficial com o eleitorado. O local do 2º turno vem da própria seção
    no 2º turno quando o nome bate; senão, de um local com o mesmo nome no município."""
    alt = alt.rename(columns={"QT_ELEITORES": "QT_ELEITORES_LISTA"})
    junta = ["SG_UF", "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO"]
    for d in (alt, t1, t2):
        for c in ("NR_ZONA", "NR_SECAO"):
            d[c] = pd.to_numeric(d[c]).astype("Int64")

    m = alt.merge(t1[CHAVE + LOCAL], on=junta, how="left")
    m = m.merge(t2[junta + LOCAL], on=junta, how="left", suffixes=("_1T", "_2T"))

    # nome da lista oficial manda; o resto do local 2T só vale se for o mesmo local
    final = nome_local(m["NM_LOCAL_VOTACAO_FINAL"])
    mesmo = final == nome_local(m["NM_LOCAL_VOTACAO_2T"])
    m["ORIGEM_LOCAL_2T"] = mesmo.map({True: "secao_2t", False: ""})
    cols_2t = [f"{c}_2T" for c in LOCAL]
    m.loc[~mesmo, cols_2t] = pd.NA

    locais = (df[["CD_MUNICIPIO"] + LOCAL].assign(_nome=lambda d: nome_local(d["NM_LOCAL_VOTACAO"]))
              .drop_duplicates(["CD_MUNICIPIO", "_nome"]))
    busca = (m.loc[~mesmo, ["CD_MUNICIPIO"]].assign(_nome=final[~mesmo])
             .reset_index().merge(locais, on=["CD_MUNICIPIO", "_nome"], how="inner").set_index("index"))
    for c in LOCAL:
        m.loc[busca.index, f"{c}_2T"] = busca[c]
    m.loc[busca.index, "ORIGEM_LOCAL_2T"] = "mesmo_nome_no_municipio"
    m.loc[m["ORIGEM_LOCAL_2T"] == "", "ORIGEM_LOCAL_2T"] = "nao_encontrado"
    m["NM_LOCAL_VOTACAO_2T"] = m["NM_LOCAL_VOTACAO_FINAL"]
    m["MOTIVO"] = "local;"
    return m[CHAVE + [f"{c}_1T" for c in LOCAL] + cols_2t
             + ["NM_LOCAL_VOTACAO_INICIAL", "QT_ELEITORES_LISTA", "ORIGEM_LOCAL_2T", "MOTIVO"]]


def main(caminho, nome_freeze):
    sys.stdout.reconfigure(encoding="utf-8")
    SAIDA = freeze.SAIDA / nome_freeze
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"Freeze {nome_freeze} — eleitorado: {caminho}")
    df = ler(caminho)
    df.columns = df.columns.str.strip()
    # remove voto em trânsito (VT) – não é seção física de um local fixo
    df = df[df["SG_UF"] != "VT"]

    turnos = sorted(df["NR_TURNO"].dropna().unique())
    print("Turnos presentes no eleitorado:", turnos)
    t1 = df[df["NR_TURNO"] == "1"].copy()
    t2 = df[df["NR_TURNO"] == "2"].copy()
    resumo = {
        "freeze": nome_freeze,
        "coletado_em": freeze.coletado_em(nome_freeze).isoformat(),
        "gerado_em": df["DT_GERACAO"].iloc[0] + " " + df["HH_GERACAO"].iloc[0],
        "secoes_1t": len(t1),
        "secoes_2t": len(t2),
        "eleitores_1t": int(pd.to_numeric(t1["QT_ELEITOR_SECAO"]).sum()),
    }

    # ---------- 1) Seções agregadas no 1º turno ----------
    agreg = t1[t1["CD_TIPO_SECAO_AGREGADA"] == "2"]
    cols = [c for c in CHAVE + TIPO + LOCAL + ["QT_ELEITOR_SECAO"] if c in agreg.columns]
    agreg[cols].sort_values(CHAVE).to_csv(
        SAIDA / "secoes_agregadas_1t.csv", sep=";", index=False, encoding="utf-8-sig")
    print(f"Seções agregadas no 1º turno: {len(agreg):,}")

    # um JSON por UF, todos com o mesmo schema, para o mapa das agregadas (exterior fica de fora)
    pasta_uf = SAIDA / "agregadas_uf"
    pasta_uf.mkdir(exist_ok=True)
    for uf, g in agreg[agreg["SG_UF"] != "ZZ"].groupby("SG_UF"):
        regs = sorted((registro_agregada(r) for r in g.to_dict("records")),
                      key=lambda d: (d["municipio"], d["zona"] or 0, d["secao"] or 0))
        (pasta_uf / f"{uf}.json").write_text(
            json.dumps(regs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    secoes_uf = t1.groupby("SG_UF").size()
    agreg_uf = agreg.groupby("SG_UF").agg(
        secoes=("NR_SECAO", "size"),
        eleitores=("QT_ELEITOR_SECAO", lambda s: int(pd.to_numeric(s).sum())))
    resumo["agregadas"] = {
        "total": len(agreg),
        "eleitores": int(agreg_uf["eleitores"].sum()),
        "por_uf": [
            {"uf": uf, "secoes": int(r.secoes), "eleitores": int(r.eleitores),
             "secoes_uf": int(secoes_uf[uf])}
            for uf, r in agreg_uf.sort_values("secoes", ascending=False).iterrows()
        ],
    }

    # ---------- 2) Mudança de local entre 1º e 2º turno (lista oficial do freeze) ----------
    alt, gerada, arquivo = ler_alteradas(freeze.DADOS / nome_freeze)
    print(f"\nLista oficial de seções alteradas ({arquivo}, gerada pelo TSE em "
          f"{gerada or 'data não informada'}): {len(alt):,}")
    mud = mudancas_oficiais(alt, t1, t2, df)
    mud.sort_values(CHAVE).to_csv(
        SAIDA / "secoes_mudanca_local_1t_2t.csv", sep=";", index=False, encoding="utf-8-sig")
    sem_1t = int(mud["CD_MUNICIPIO"].isna().sum())
    origem = mud["ORIGEM_LOCAL_2T"].value_counts()
    print(f"  sem a seção no eleitorado (sem local/coordenada do 1º turno): {sem_1t}")
    print("  local do 2º turno:", origem.to_dict())

    por_uf = mud.groupby("SG_UF").size()
    por_mun = mud.groupby(["SG_UF", "NM_MUNICIPIO"]).size().sort_values(ascending=False)
    resumo["mudancas"] = {
        "fonte": arquivo,
        "lista_gerada_tse": gerada,
        "total": len(mud),
        "local": len(mud),
        "sem_secao_eleitorado": sem_1t,
        "local_2t": {k: int(v) for k, v in origem.items()},
        "por_uf": [
            {"uf": uf, "local": int(n), "endereco": 0, "secoes_uf": int(secoes_uf.get(uf, 0))}
            for uf, n in por_uf.sort_values(ascending=False).items()
        ],
        "top_municipios": [
            {"uf": uf, "municipio": mun, "secoes": int(n)} for (uf, mun), n in por_mun.head(15).items()
        ],
    }
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    freeze.registrar()
    print(f"\nArquivos gravados em {SAIDA}")


if __name__ == "__main__":
    nome, args = freeze.escolher(sys.argv[1:])
    if len(args) > 1:
        sys.exit(__doc__)
    main(args[0] if args else str(ELEITORADO), nome)
