"""
Publica no dashboard os arquivos de um freeze, a partir das saídas da extração.

Entradas (do freeze mais recente, ou do informado em --freeze):
  extracao/saida/<freeze>/resumo.json, agregadas_uf/, secoes_mudanca_local_1t_2t.csv
  e votos_secoes_mudanca_1t.csv
  extracao/saida/freezes.csv

Uso:
    uv run extracao/painel.py [--freeze 2026-10-19_1708]

Saída em dashboard/data/<freeze>/: totais.csv, por_uf.csv, mudancas.csv, votos_mapa.csv,
candidatos.csv, resumo.json e agregadas_uf/<UF>.json; e dashboard/data/freezes.csv.
Esses arquivos são versionados: depois de rodar, é só commitar e dar push.
"""
import json
import shutil
import sys

import pandas as pd

import freeze

CHAVE_ID = ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"]


def endereco(df, t):
    """'RUA X, 10 — BAIRRO', como o painel mostra."""
    partes = df[[f"DS_ENDERECO_{t}", f"NM_BAIRRO_{t}"]].fillna("")
    return partes.apply(lambda r: " — ".join(v for v in r if v), axis=1)


def coordenada(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "."), errors="coerce")


def main(nome_freeze):
    sys.stdout.reconfigure(encoding="utf-8")
    pasta = freeze.SAIDA / nome_freeze
    destino = freeze.PAINEL / nome_freeze
    destino.mkdir(parents=True, exist_ok=True)

    resumo = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
    mud = pd.read_csv(pasta / "secoes_mudanca_local_1t_2t.csv", sep=";", encoding="utf-8-sig", dtype=str)
    mud["id"] = mud[CHAVE_ID].astype(str).agg("-".join, axis=1)
    mud["eleitores"] = pd.to_numeric(mud["QT_ELEITORES_LISTA"]).astype("Int64")
    sem_coord_2t = int(coordenada(mud["NR_LATITUDE_2T"]).isna().sum())

    ag = resumo["agregadas"]
    pd.DataFrame([{
        "secoes_1t": resumo["secoes_1t"],
        "eleitores_1t": resumo["eleitores_1t"],
        "agregadas": ag["total"],
        "eleitores_agregadas": ag["eleitores"],
        "mudancas": len(mud),
        "eleitores_mudancas": int(mud["eleitores"].sum()),
        "sem_coord_2t": sem_coord_2t,
    }]).to_csv(destino / "totais.csv", index=False)

    agreg_uf = pd.DataFrame(ag["por_uf"]).rename(columns={"secoes": "agregadas", "eleitores": "eleitores_agregadas"})
    mud_uf = mud.groupby("SG_UF").agg(mud_total=("id", "size"), eleitores_mud=("eleitores", "sum")).reset_index()
    por_uf = (agreg_uf.merge(mud_uf.rename(columns={"SG_UF": "uf"}), on="uf", how="outer")
              .fillna({"agregadas": 0, "eleitores_agregadas": 0, "mud_total": 0, "eleitores_mud": 0}))
    por_uf["pct_agregadas"] = (por_uf["agregadas"] / por_uf["secoes_uf"]).round(4)
    por_uf[["uf", "secoes_uf", "agregadas", "pct_agregadas", "eleitores_agregadas", "mud_total", "eleitores_mud"]] \
        .astype({"agregadas": int, "eleitores_agregadas": int, "mud_total": int, "eleitores_mud": int}) \
        .sort_values("agregadas", ascending=False).to_csv(destino / "por_uf.csv", index=False)

    base = pd.DataFrame({
        "id": mud["id"], "uf": mud["SG_UF"], "municipio": mud["NM_MUNICIPIO"],
        "zona": mud["NR_ZONA"], "secao": mud["NR_SECAO"], "motivo": "Local",
    })
    pd.concat([base, pd.DataFrame({
        "local_1t": mud["NM_LOCAL_VOTACAO_1T"], "local_2t": mud["NM_LOCAL_VOTACAO_2T"],
        "endereco_2t": mud["DS_ENDERECO_2T"], "eleitores": mud["eleitores"],
        "origem_local_2t": mud["ORIGEM_LOCAL_2T"],
    })], axis=1).to_csv(destino / "mudancas.csv", index=False)

    votos = pd.read_csv(pasta / "votos_secoes_mudanca_1t.csv", sep=";", encoding="utf-8-sig", dtype=str)
    votos["id"] = votos[CHAVE_ID].astype(str).agg("-".join, axis=1)
    candidatos = [c for c in votos.columns if " - " in c]
    mapa = pd.DataFrame({
        "id": votos["id"], "uf": votos["SG_UF"], "municipio": votos["NM_MUNICIPIO"],
        "zona": votos["NR_ZONA"], "secao": votos["NR_SECAO"], "motivo": "Local",
        "local_1t": votos["NM_LOCAL_VOTACAO_1T"], "endereco_1t": endereco(votos, "1T"),
        "lat_1t": coordenada(votos["NR_LATITUDE_1T"]), "lon_1t": coordenada(votos["NR_LONGITUDE_1T"]),
        "local_2t": votos["NM_LOCAL_VOTACAO_2T"], "endereco_2t": endereco(votos, "2T"),
        "lat_2t": coordenada(votos["NR_LATITUDE_2T"]), "lon_2t": coordenada(votos["NR_LONGITUDE_2T"]),
    })
    for c in candidatos:
        mapa[f"v{c.split(' - ')[0]}"] = votos[c]
    mapa["total"] = votos["TOTAL_VOTOS"]
    mapa.to_csv(destino / "votos_mapa.csv", index=False)
    pd.DataFrame([c.split(" - ", 1) for c in candidatos], columns=["nr", "nome"]) \
        .to_csv(destino / "candidatos.csv", index=False)

    # resumo e agregadas por UF vão como saíram da extração
    shutil.copy(pasta / "resumo.json", destino / "resumo.json")
    shutil.copytree(pasta / "agregadas_uf", destino / "agregadas_uf", dirs_exist_ok=True)
    shutil.copy(freeze.SAIDA / "freezes.csv", freeze.PAINEL / "freezes.csv")
    print(f"Freeze {nome_freeze}: {len(mud)} seções alteradas, {len(mapa)} com votos, "
          f"{sem_coord_2t} sem coordenada no 2º turno")
    print(f"Arquivos do painel em {destino}")


if __name__ == "__main__":
    nome, args = freeze.escolher(sys.argv[1:])
    if args:
        sys.exit(__doc__)
    main(nome)
