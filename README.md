# Seções TSE 2026

Análise das seções eleitorais de 2026 a partir dos Dados Abertos do TSE:

1. seções **agregadas** no 1º turno (eleitorado por local de votação);
2. seções que **mudaram de local** entre o 1º e o 2º turno, segundo a **lista oficial do TSE**,
   com os votos do 1º turno em cada uma.

O repositório tem duas frentes:

- **`extracao/`**: scripts Python que leem as bases do TSE e geram os arquivos do painel;
- **`dashboard/`**: o painel, um site estático publicado no GitHub Pages que lê os freezes
  versionados em `dashboard/data/`.

## Estrutura

```
pyproject.toml, uv.lock          dependências da extração (uv)

extracao/
  freeze.py                      cria e lista os freezes (coletas datadas da lista oficial)
  secoes_tse_2026.py             agregadas + seções alteradas do freeze
  votos_secoes_mudanca.py        votos do 1º turno nas seções alteradas
  painel.py                      publica os arquivos do freeze em dashboard/data/
  votos_primeiro_turno.py        baixa os votos por seção (uma vez só)
  dados/geral/                   bases que não mudam (não versionadas):
                                   eleitorado_local_votacao_2026.zip
                                   votos_presidente_por_secao_2026.csv
  dados/AAAA-MM-DD_HHMM/         um freeze: a lista oficial baixada nessa hora + freeze.json
  saida/AAAA-MM-DD_HHMM/         intermediários gerados a partir desse freeze (não versionados)
  saida/freezes.csv              um freeze por linha

dashboard/                       publicado no GitHub Pages (versionado)
  index.html, dash.js, estilo.css
  static/ufs.json                contorno dos estados (fundo dos mapas)
  data/freezes.csv               freezes registrados; o painel abre no mais recente
  data/AAAA-MM-DD_HHMM/          tudo que o painel lê de um freeze

.github/workflows/pages.yml      publica dashboard/ a cada push na main
```

`extracao/dados/` e `extracao/saida/` ficam fora do git (`.gitignore`): são os brutos do TSE
(~1 GB) e os CSVs intermediários. Tudo que alimenta o painel vai para `dashboard/data/` e é
versionado.

## Freezes temporais

O TSE publica e **atualiza ao longo do dia** a lista oficial de seções alteradas no
2º turno (`secoes_eleitorais_alteradas_2t-pais_2026`). Cada download é um **freeze**:
uma pasta com a data e hora da coleta (horário de Brasília). Os scripts usam sempre o
freeze **mais recente**, a menos que se passe `--freeze <nome>`. O painel abre no mais
recente e tem um seletor no topo para ver os anteriores (`?freeze=AAAA-MM-DD_HHMM` na URL).

A lista é aceita em dois formatos; basta salvar **um** deles na pasta do freeze:

1. **CSV** (mais fácil) — [tse.jus.br](https://www.tse.jus.br): Home > Eleitorado da eleição > Capilaridade.
2. **CSV zipado** — Portal de Dados Abertos, conjunto [Eleitorado 2026](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026)
   (`secoes_eleitorais_alteradas_2t-pais_2026.csv.zip`). Também informa quando o TSE gerou o arquivo.

Se os dois estiverem na pasta, o zip é usado.

O eleitorado e os votos do 1º turno não mudam mais e ficam em `extracao/dados/geral/`, fora dos freezes.

## Atualizar os dados (a cada nova versão da lista)

Confira várias vezes ao dia se o TSE publicou uma lista nova e, a cada uma, na raiz do repositório:

```
uv run extracao/freeze.py novo            # cria extracao/dados/<agora>/ (ou: novo 2026-10-19_1708)
# salve a lista oficial (CSV da Capilaridade ou zip dos Dados Abertos) em extracao/dados/<agora>/
uv run extracao/secoes_tse_2026.py        # gera extracao/saida/<agora>/ e atualiza freezes.csv
uv run extracao/votos_secoes_mudanca.py   # votos do 1º turno nas seções alteradas
uv run extracao/painel.py                 # publica em dashboard/data/<agora>/ e data/freezes.csv
uv run extracao/freeze.py                 # confere a lista de freezes
git add dashboard/data && git commit -m "Freeze <agora>" && git push
```

O push na `main` dispara o workflow que republica o painel.

### Preparação (uma vez só)

```
# eleitorado_local_votacao_2026.zip: Portal de Dados Abertos > Eleitorado 2026 → extracao/dados/geral/
uv run extracao/votos_primeiro_turno.py   # baixa e filtra os votos → extracao/dados/geral/
```

No GitHub: Settings > Pages > Build and deployment > Source = **GitHub Actions**.

## Dashboard

Site estático, sem build: `index.html` traz a página, `dash.js` é um runtime pequeno que
carrega os arquivos de `data/` sob demanda (os JSON de agregadas só quando a UF é escolhida)
e `estilo.css` define as cores, claro e escuro. O d3 vem do cdnjs.

Para ver localmente (o `fetch` não funciona abrindo o arquivo direto):

```
uv run python -m http.server -d dashboard 8000   # http://localhost:8000/
```

### Arquivos de cada freeze (`dashboard/data/<freeze>/`)

| Arquivo | Conteúdo |
|---|---|
| `totais.csv` | totais nacionais: seções e eleitores do 1º turno, agregadas, seções alteradas, sem coordenada no 2º turno |
| `por_uf.csv` | agregadas e seções alteradas por UF |
| `mudancas.csv` | uma linha por seção alterada, com os locais dos dois turnos |
| `votos_mapa.csv` | seções alteradas com coordenadas dos dois turnos e votos por candidato (`v<número>`) |
| `candidatos.csv` | número e nome de cada candidato, mais 95 (branco) e 96 (nulo) |
| `resumo.json` | totais, por UF e municípios com mais mudanças, data de geração da lista |
| `agregadas_uf/<UF>.json` | seções agregadas da UF (sem o exterior): `uf, cd_municipio, municipio, zona, secao, secao_principal, nr_local, local, endereco, bairro, cep, lat, lon, eleitores` |

`data/freezes.csv`: `freeze, coletado_em, lista_gerada_tse, secoes_alteradas, eleitorado_gerado_tse, processado`.

## Intermediários da extração (em `extracao/saida/<freeze>/`, não versionados)

| Arquivo | Conteúdo |
|---|---|
| `secoes_agregadas_1t.csv` | seções com `CD_TIPO_SECAO_AGREGADA = 2` no 1º turno |
| `secoes_mudanca_local_1t_2t.csv` | seções da lista oficial, com local, endereço e coordenadas dos dois turnos vindos do eleitorado, eleitores da lista e `ORIGEM_LOCAL_2T` |
| `votos_secoes_mudanca_1t.csv` | votos para Presidente no 1º turno (uma coluna por candidato, brancos, nulos e total) em cada seção alterada |
| `resumo.json`, `agregadas_uf/` | copiados para o dashboard pelo `painel.py` |

## Notas sobre os dados

- O zip do eleitorado traz `_BRASIL.csv` e um CSV por UF com as mesmas linhas; o script usa só o `_BRASIL` para não duplicar.
- Nulos conforme o LEIAME: `#NULO` / `-1` (em branco) e `#NE` / `-3` (não registrado) viram vazio.
- `ZZ` = exterior. Voto em trânsito (`VT`) é descartado.
- A lista oficial só traz o **nome** do local final. Endereço e coordenadas do novo local vêm
  da linha do 2º turno da seção no eleitorado quando o nome bate (`secao_2t`); senão, de um
  local com o mesmo nome no município (`mesmo_nome_no_municipio`); senão ficam vazios
  (`nao_encontrado`). Os nomes são comparados sem acento e sem pontuação, porque a lista
  troca `.` por `,` (`E, M, JOAO GOULART`).
- A data de geração da lista só é conhecida no formato zipado; com o CSV da Capilaridade fica vazia.
- O contorno dos estados (`dashboard/static/ufs.json`) vem do `brazil-states.geojson` do projeto
  [click_that_hood](https://github.com/codeforgermany/click_that_hood), simplificado.
