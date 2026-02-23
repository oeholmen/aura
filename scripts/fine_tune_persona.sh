#!/usr/bin/env bash
# Fine-tune helper (template). Update variables below before running.
set -euo pipefail
# Edit these values:
BASE_MODEL="/path/to/base/model-or-hf-id"
TRAIN_FILE="data/personality_training/aura.jsonl"
OUTPUT_DIR="outputs/aura-finetuned"
BATCH_SIZE=4
EPOCHS=3
LR=2e-4

echo "This script prints a recommended accelerate/transformers command for fine-tuning using PEFT (LoRA)."
echo
echo "Requirements: python packages: accelerate, transformers, peft, datasets, bitsandbytes (optional for 8-bit), accelerate configured."
echo
echo "Example command (do not run until you set BASE_MODEL and have accelerate configured):"
echo
printf '%s\n' "accelerate launch --num_processes 1 --num_machines 1 --mixed_precision fp16 run_clm.py \"
printf '%s\n' "  --model_name_or_path \"$BASE_MODEL\" \"
printf '%s\n' "  --train_file \"$TRAIN_FILE\" \"
printf '%s\n' "  --do_train \"
printf '%s\n' "  --output_dir \"$OUTPUT_DIR\" \"
printf '%s\n' "  --per_device_train_batch_size $BATCH_SIZE \"
printf '%s\n' "  --learning_rate $LR \"
printf '%s\n' "  --num_train_epochs $EPOCHS \"
printf '%s\n' "  --overwrite_output_dir --fp16"

echo
echo "If you want a LoRA/PEFT workflow, use a training script that supports peft and add the peft args (r, alpha, target modules)."
echo "I can start training if you confirm the base model path and GPU/accelerate readiness."
