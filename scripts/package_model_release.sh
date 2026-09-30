#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_path="$repo_root/model-release.env"

# shellcheck disable=SC1090
source "$config_path"

model_dir="$repo_root/models/bertimbau-citations"
output_dir="$repo_root/dist"
archive_path="$output_dir/$MODEL_ARCHIVE_NAME"

required_files=(
  config.json
  model.safetensors
  special_tokens_map.json
  tokenizer.json
  tokenizer_config.json
  vocab.txt
)

for filename in "${required_files[@]}"; do
  if [[ ! -f "$model_dir/$filename" ]]; then
    echo "Artefato ausente: $model_dir/$filename" >&2
    exit 1
  fi
done

echo "$MODEL_WEIGHTS_SHA256  $model_dir/model.safetensors" | sha256sum --check --status || {
  echo "O hash dos pesos não corresponde ao aprovado em model-release.env" >&2
  exit 1
}

mkdir -p "$output_dir"
temporary_archive="$(mktemp "$output_dir/.model-release.XXXXXX.tar.gz")"
staging_dir="$(mktemp -d)"
trap 'rm -f "$temporary_archive"; rm -rf "$staging_dir"' EXIT

# O asset deve carregar consigo licença, atribuições e model card, mesmo quando
# for baixado fora do repositório.
mkdir -p "$staging_dir/bertimbau-citations"
for filename in "${required_files[@]}"; do
  cp "$model_dir/$filename" "$staging_dir/bertimbau-citations/$filename"
done
cp "$repo_root/LICENSE" "$staging_dir/bertimbau-citations/LICENSE"
cp "$repo_root/MODEL_CARD.md" "$staging_dir/bertimbau-citations/MODEL_CARD.md"
cp "$repo_root/THIRD_PARTY_NOTICES.md" \
  "$staging_dir/bertimbau-citations/THIRD_PARTY_NOTICES.md"

# Ordenação, metadados e timestamp fixos tornam o pacote reproduzível.
tar --sort=name \
  --mtime='UTC 1970-01-01' \
  --owner=0 --group=0 --numeric-owner \
  -C "$staging_dir" \
  -cf - bertimbau-citations | gzip -n > "$temporary_archive"

mv "$temporary_archive" "$archive_path"
rm -rf "$staging_dir"
trap - EXIT

archive_sha256="$(sha256sum "$archive_path" | awk '{print $1}')"
archive_size="$(stat -c '%s' "$archive_path")"

printf 'Pacote: %s\nSHA-256: %s\nBytes: %s\n' \
  "$archive_path" "$archive_sha256" "$archive_size"
printf '\nAtualize MODEL_ARCHIVE_SHA256 em %s antes do commit final.\n' "$config_path"
