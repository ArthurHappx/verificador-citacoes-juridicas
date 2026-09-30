# Execução rápida

Este guia executa o Verificador de Citações Jurídicas a partir de um SQLite canônico e de uma pasta com documentos `.txt` de input.

## Entradas necessárias

- `<caminho_db>`: banco SQLite no formato descrito no README;
- `<pasta_txt>`: pasta com um ou mais arquivos `.txt` UTF-8 (sem BOM);
- `<arquivo_saida.csv>`: caminho onde o CSV final será criado.

## Opção recomendada: Docker com GPU

Na raiz do repositório, baixe e valide o checkpoint:

```bash
./scripts/download_model.sh
```

Construa a imagem:

```bash
docker build -t legal-citation-verifier:1.0.0 .
```

Crie a pasta de saída e execute sem acesso à internet:

```bash
mkdir -p output

docker run --rm --network none --gpus all \
  -v "/caminho/absoluto/base.db:/input/base.db:ro" \
  -v "/caminho/absoluto/txt:/input/txt:ro" \
  -v "$PWD/output:/output" \
  legal-citation-verifier:1.0.0 \
  /input/base.db /input/txt /output/submission.csv --device cuda
```

O resultado principal será `output/submission.csv`.

## Execução local

Com as dependências de `requirements.txt` instaladas e os pesos já baixados:

```bash
bash run.sh \
  /caminho/absoluto/base.db \
  /caminho/absoluto/txt \
  /caminho/absoluto/output/submission.csv \
  --device cuda
```

Para testar sem GPU, use `--device cpu`. No Docker, remova também a opção `--gpus all`.

## Arquivos gerados

Ao lado do CSV, o pipeline grava:

```text
output/
├── submission.csv
├── canonical_index.sqlite
├── run_summary.json
└── enriched_json/
    └── <documento_id>.json
```

O índice é construído automaticamente a partir do banco recebido. Não é necessário fornecer um `canonical_index.sqlite` pré-computado.

## Ajuda e diagnóstico

```bash
bash run.sh --help
```

Se o checkpoint estiver ausente ou com hash incorreto, execute novamente:

```bash
./scripts/download_model.sh
```

Para detalhes da abordagem, contrato da base, execução com release privada e testes, consulte o[README completo](README.md).
