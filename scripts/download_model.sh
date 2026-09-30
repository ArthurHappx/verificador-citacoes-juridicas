#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_path="$repo_root/model-release.env"

# shellcheck disable=SC1090
source "$config_path"

target_dir="$repo_root/models/bertimbau-citations"
target_weights="$target_dir/model.safetensors"

if [[ -f "$target_weights" ]]; then
  if echo "$MODEL_WEIGHTS_SHA256  $target_weights" | sha256sum --check --status; then
    echo "Modelo já está instalado e possui o SHA-256 esperado."
    exit 0
  fi
  echo "Já existe um modelo local com hash diferente; não será sobrescrito." >&2
  exit 3
fi

command -v tar >/dev/null || { echo "tar não está instalado" >&2; exit 4; }

temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT
archive_path="$temporary_dir/$MODEL_ARCHIVE_NAME"

if [[ $# -gt 1 ]]; then
  echo "uso: $0 [arquivo_do_modelo.tar.gz]" >&2
  exit 8
fi

if [[ $# -eq 1 ]]; then
  source_archive="$1"
  [[ -f "$source_archive" ]] || { echo "Pacote local não encontrado: $source_archive" >&2; exit 8; }
  cp "$source_archive" "$archive_path"
else
  if [[ "$MODEL_RELEASE_URL" == SET_* || "$MODEL_ARCHIVE_SHA256" == SET_* ]]; then
    echo "model-release.env ainda não contém URL e SHA-256 finais da release." >&2
    exit 2
  fi
  command -v curl >/dev/null || { echo "curl não está instalado" >&2; exit 4; }
  curl_args=(--fail --location --retry 3 --output "$archive_path")
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    curl_args+=(--header "Authorization: Bearer $GITHUB_TOKEN")
  fi
  curl "${curl_args[@]}" "$MODEL_RELEASE_URL"
fi
echo "$MODEL_ARCHIVE_SHA256  $archive_path" | sha256sum --check --status || {
  echo "Falha na verificação SHA-256 do pacote do modelo." >&2
  exit 5
}

tar -xzf "$archive_path" -C "$temporary_dir"
staged_model="$temporary_dir/bertimbau-citations"
if [[ ! -d "$staged_model" ]]; then
  # Aceita também o diretório externo criado ao compactar a pasta da release.
  staged_model="$temporary_dir/${MODEL_ARCHIVE_NAME%.tar.gz}/bertimbau-citations"
fi
staged_weights="$staged_model/model.safetensors"

if [[ ! -f "$staged_weights" ]]; then
  echo "O pacote não contém bertimbau-citations/model.safetensors." >&2
  exit 6
fi
echo "$MODEL_WEIGHTS_SHA256  $staged_weights" | sha256sum --check --status || {
  echo "Falha na verificação SHA-256 dos pesos extraídos." >&2
  exit 7
}

mkdir -p "$repo_root/models"
mv "$staged_model" "$target_dir"
echo "Modelo instalado e verificado em $target_dir"
