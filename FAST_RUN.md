# Execução rápida

Na raiz do repositório, coloque o banco em `input/base.db` e os documentos `.txt` UTF-8 em `input/txt/`. Ajuste os caminhos abaixo se necessário; `$PWD` representa o diretório atual.

## Docker

Prepare os pesos e a imagem com acesso à internet:

```bash
./scripts/download_model.sh
docker build -t legal-citation-verifier:1.0.0 .
mkdir -p output
```

**Antes de usar GPU**, verifique o acesso pelo Docker (requer driver NVIDIA e NVIDIA Container Toolkit):

```bash
docker run --rm --gpus all ubuntu nvidia-smi
```

Se o erro exigir o runtime NVIDIA, adicione `--runtime=nvidia` à checagem e à execução. Para executar em CPU, remova `--gpus all` e use `--device cpu`.

Execute o pipeline sem acesso à internet:

```bash
docker run --rm --network none --gpus all \
  -v "$PWD/input/base.db:/input/base.db:ro" \
  -v "$PWD/input/txt:/input/txt:ro" \
  -v "$PWD/output:/output" \
  legal-citation-verifier:1.0.0 \
  /input/base.db /input/txt /output/submission.csv --device cuda
```

## Execução local

Com as dependências de `requirements.txt` instaladas e os pesos baixados:

```bash
bash run.sh \
  "$PWD/input/base.db" \
  "$PWD/input/txt" \
  "$PWD/output/submission.csv" \
  --device cpu
```

Use `--device cuda` se CUDA estiver disponível no seu ambiente PyTorch. CPU dispensa configurar GPU; no lote medido de 26 documentos, GPU levou em média 19,8 s contra 47,0 s em CPU. O ganho depende do hardware; veja as [condições da medição](README.md#cpu-ou-gpu-desempenho-medido).

O resultado é `output/submission.csv`; índice, resumo e JSONs também ficam em `output/`.

Para opções, execute `bash run.sh --help`. Consulte o [README](README.md) para requisitos e diagnóstico.
