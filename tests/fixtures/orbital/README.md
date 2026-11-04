# Fixtures de ingestão orbital (dados públicos reais)

Recortes **sem nenhuma alteração de valores** de arquivos públicos baixados em 04/11/2026, entre 03:29 e 03:31 UTC, sem credenciais.
Cada recorte mantém o cabeçalho original e só as linhas dentro do envelope do Ceará (`CEARA_BBOX`: lon −41,5 a −37,2; lat −7,9 a −2,7).
É o mesmo recorte que a API de área da NASA FIRMS devolveria para esse bbox.

| Fixture | Origem (URL pública) | Linhas no original | Linhas no recorte | SHA-256 do original |
|---|---|---|---|---|
| `firms_VIIRS_SNPP_NRT.csv` | `https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_24h.csv` | 851 | 11 | `89db8dfe03e4cd1178841afe2676d11bf2795e793ee4f050c7625975fef04122` |
| `firms_VIIRS_NOAA20_NRT.csv` | `…/noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_24h.csv` | 15.210 | 227 | `bc1a2a70bb853364b3313d00cd6d1908038d325e50c6b8e9d7f8631c2c331bb7` |
| `firms_VIIRS_NOAA21_NRT.csv` | `…/noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_24h.csv` | 14.976 | 210 | `b58d1d7b9b8ff03394ab1e5fc319c24ed75f67424694d9eeba601da7dfc3afd0` |
| `firms_MODIS_NRT.csv` | `…/modis-c6.1/csv/MODIS_C6_1_South_America_24h.csv` | 5.106 | 133 | `67449c3f6a3edba43b815458ead5169dd3d1028cd2a1896c8da0622b9d1413e9` |
| `data/samples/inpe/focos_diario_br_20261103.csv` (fora desta pasta: vai na imagem, para validação local sem rede) | `https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_20261103.csv` (versão com `Last-Modified: Wed, 04 Nov 2026 03:05:02 GMT`) | 14.516 | 511 | `6b3fbe4112248e23051258d1dd606ea9728e1a95925af239daa83881724d37a0` |

## Seleção

FIRMS: `awk -F, 'NR==1 || ($2>-41.5 && $2<-37.2 && $1>-7.9 && $1<-2.7)'`.

INPE: as linhas dentro do envelope e, para testar o descarte fora do bbox, uma a cada 1.000 linhas do Brasil inteiro:
```
awk -F, 'NR==1 || ($3+0>-41.5 && $3+0<-37.2 && $2+0>-7.9 && $2+0<-2.7) || (NR%1000==0)'
```

## Limites dessas fixtures

- **Coluna `instrument`:** os arquivos públicos de 24 h da FIRMS têm as mesmas colunas da API de área, exceto `instrument`, que a API pode incluir. O adaptador aceita os dois formatos, e um teste cobre a variante com a coluna.
- **Uso:** as fixtures servem para validar o formato e o processamento. Elas **não** provam que a API de área da FIRMS responde com uma chave válida, porque nenhuma chave foi usada (ver `docs/IGNIS/SPRINT-1.2-DELIVERY.md`).
- **Dados pessoais:** não há. O conteúdo é a posição de anomalias térmicas e os nomes de municípios.
