"""
Freezes temporais da lista oficial de seções alteradas no 2º turno.

O TSE republica ao longo do dia a lista `secoes_eleitorais_alteradas_2t-pais_2026`,
aceita em dois formatos (salve um deles na pasta do freeze):
  1) .csv     — tse.jus.br: Home > Eleitorado da eleição > Capilaridade (mais fácil)
  2) .csv.zip — Portal de Dados Abertos, conjunto Eleitorado 2026 (traz a data de geração)
Cada download fica numa pasta nomeada pelo momento da coleta (AAAA-MM-DD_HHMM,
horário de Brasília), e a análise sempre usa a mais recente:

    extracao/dados/geral/            bases que não mudam: eleitorado_local_votacao_2026.zip
                                     e votos_presidente_por_secao_2026.csv
    extracao/dados/2026-10-19_1708/  a lista oficial baixada nessa coleta + freeze.json
    extracao/saida/2026-10-19_1708/  tudo que os scripts geraram a partir dela
    extracao/saida/freezes.csv       um freeze por linha (o painel.py copia para o dashboard)

Uso:
    uv run extracao/freeze.py                       # lista os freezes
    uv run extracao/freeze.py novo                  # cria o freeze de agora
    uv run extracao/freeze.py novo 2026-10-19_1708  # cria um freeze com data/hora informada

Os outros scripts usam o freeze mais recente, ou o informado em --freeze <nome>.
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DADOS = RAIZ / "dados"
GERAL = DADOS / "geral"
SAIDA = RAIZ / "saida"
PAINEL = RAIZ.parent / "dashboard" / "data"  # o que o dashboard lê (versionado)
ALTERADAS = "secoes_eleitorais_alteradas_2t"
BRASILIA = timezone(timedelta(hours=-3))
FORMATO = "%Y-%m-%d_%H%M"
COLUNAS = ["freeze", "coletado_em", "lista_gerada_tse", "secoes_alteradas",
           "eleitorado_gerado_tse", "processado"]


def coletado_em(nome):
    """Momento da coleta a partir do nome da pasta (ValueError se não for um freeze)."""
    return datetime.strptime(nome, FORMATO).replace(tzinfo=BRASILIA)


def freezes():
    """Nomes dos freezes em dados/, do mais antigo ao mais recente."""
    nomes = []
    for p in DADOS.iterdir() if DADOS.exists() else []:
        try:
            coletado_em(p.name)
        except ValueError:
            continue
        if p.is_dir():
            nomes.append(p.name)
    return sorted(nomes)


def escolher(argv):
    """Tira `--freeze <nome>` de argv e devolve (nome, resto); sem a opção, o mais recente."""
    argv = list(argv)
    if "--freeze" in argv:
        i = argv.index("--freeze")
        nome = argv[i + 1]
        del argv[i:i + 2]
        coletado_em(nome)
    else:
        todos = freezes()
        if not todos:
            sys.exit("Nenhum freeze em dados/. Crie um com: uv run extracao/freeze.py novo")
        nome = todos[-1]
    if not (DADOS / nome).is_dir():
        sys.exit(f"Freeze {nome} não existe em dados/.")
    return nome, argv


def lista_alteradas(pasta):
    """Arquivo da lista oficial no freeze: o .zip se houver (tem a data de geração), senão o .csv."""
    achados = [p for p in Path(pasta).glob(f"{ALTERADAS}*") if p.suffix.lower() in (".zip", ".csv")]
    achados.sort(key=lambda p: p.suffix.lower() != ".zip")
    return achados[0] if achados else None


def novo(nome=None):
    nome = nome or datetime.now(BRASILIA).strftime(FORMATO)
    pasta = DADOS / nome
    pasta.mkdir(parents=True, exist_ok=True)
    meta = {"freeze": nome, "coletado_em": coletado_em(nome).isoformat()}
    (pasta / "freeze.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return nome


def registrar():
    """Reescreve saida/freezes.csv com todos os freezes e o que se sabe de cada um."""
    SAIDA.mkdir(exist_ok=True)
    linhas = []
    for nome in freezes():
        caminho = SAIDA / nome / "resumo.json"
        resumo = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
        mud = resumo.get("mudancas", {})
        linhas.append({
            "freeze": nome,
            "coletado_em": coletado_em(nome).isoformat(),
            "lista_gerada_tse": mud.get("lista_gerada_tse", ""),
            "secoes_alteradas": mud.get("total", ""),
            "eleitorado_gerado_tse": resumo.get("gerado_em", ""),
            "processado": "sim" if resumo else "não",
        })
    with open(SAIDA / "freezes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        w.writerows(linhas)
    return linhas


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args[:1] == ["novo"] and len(args) <= 2:
        nome = novo(args[1] if len(args) == 2 else None)
        registrar()
        print(f"Freeze criado: dados/{nome}/ — salve nele a lista {ALTERADAS}... "
              "(.csv da Capilaridade ou .csv.zip dos Dados Abertos)")
    elif not args:
        for linha in registrar():
            print(f"{linha['freeze']}  coletado em {linha['coletado_em']}  "
                  f"seções alteradas: {linha['secoes_alteradas'] or '-'}  processado: {linha['processado']}")
    else:
        sys.exit(__doc__)
