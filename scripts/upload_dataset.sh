#!/usr/bin/env bash
# Upload a dataset file to S3 or GCS. Requires configured CLI (aws or gsutil).
set -euo pipefail
if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <local-file> <remote-destination>\nExamples:\n  $0 data/personality_training/aura.jsonl s3://my-bucket/aura/aura.jsonl\n  $0 data/personality_training/aura.jsonl gs://my-bucket/aura/aura.jsonl"
  exit 2
fi
FILE="$1"
DEST="$2"
if [[ "$DEST" == s3://* ]]; then
  command -v aws >/dev/null || { echo "aws CLI not found"; exit 3; }
  aws s3 cp "$FILE" "$DEST"
elif [[ "$DEST" == gs://* ]]; then
  command -v gsutil >/dev/null || { echo "gsutil not found"; exit 3; }
  gsutil cp "$FILE" "$DEST"
else
  echo "Unknown destination scheme. Use s3:// or gs://"; exit 4
fi
echo "Uploaded $FILE -> $DEST"
