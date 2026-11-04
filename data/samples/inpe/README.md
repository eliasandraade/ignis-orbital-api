# Amostra histórica pública do INPE (fixture)

`focos_diario_br_20261103.csv` é um recorte, sem alteração de valores, do arquivo oficial
`https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_20261103.csv`
(versão `Last-Modified: Wed, 04 Nov 2026 03:05:02 GMT`, SHA-256 do original
`6b3fbe4112248e23051258d1dd606ea9728e1a95925af239daa83881724d37a0`, 14.516 linhas), baixado em
04/11/2026 sem credenciais. Contém o cabeçalho original, as 498 linhas dentro do envelope do Ceará e
13 linhas do restante do Brasil (uma a cada 1.000) para exercitar o descarte fora do bbox.

Uso: validação local quando o servidor do INPE não estiver acessível.

    python -m app.orbital.worker --inpe-fixture data/samples/inpe/focos_diario_br_20261103.csv

A execução fica registrada com `params.provenance.origin = "fixture"` e a API informa
`origin: "fixture"` na situação da fonte. São **observações reais de 03/11/2026**: os horários
(`observed_at`) são os originais e nunca são apresentados como detecções de hoje.
