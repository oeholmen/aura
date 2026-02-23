import logging
import os
import sys

# Configuration
MAX_SEQ_LENGTH = 2048
DTYPE = None 
LOAD_IN_4BIT = True 
TRAINING_DATA_FILE = "autonomy_engine/memory/training_data.jsonl"
OUTPUT_DIR = "autonomy_engine/brain/outputs"

def train_self():
    """
    Fine-tunes the local Llama 3 model on 'training_data.jsonl'.
    """
    print(">>> INITIATING CEREBRAL UPDATE (Fine-Tuning) <<<")

    # Hardware/Library Check
    try:
        import torch
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError as e:
        print(f"WARNING: Unsloth/Transformers not installed or import failed ({e}).")
        print("Skipping actual training (Simulation Mode).")
        print(">>> CEREBRAL UPDATE COMPLETE (SIMULATED). <<<")
        return

    if not torch.cuda.is_available():
        print("WARNING: No NVIDIA GPU detected. Unsloth requires CUDA.")
        print("Skipping actual training (Simulation Mode).")
        print(">>> CEREBRAL UPDATE COMPLETE (SIMULATED). <<<")
        return

    print("Loading Base Model (Llama-3-8b-Instruct)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name = "unsloth/llama-3-8b-Instruct-bnb-4bit",
        max_seq_length = MAX_SEQ_LENGTH,
        dtype = DTYPE,
        load_in_4bit = LOAD_IN_4BIT,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r = 16,
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj",],
        lora_alpha = 16,
        lora_dropout = 0, 
        bias = "none", 
        use_gradient_checkpointing = "unsloth",
    )

    if not os.path.exists(TRAINING_DATA_FILE):
        print(f"No training data found at {TRAINING_DATA_FILE}.")
        return

    dataset = load_dataset("json", data_files=TRAINING_DATA_FILE, split="train")

    print(f"Training on {len(dataset)} examples...")
    trainer = SFTTrainer(
        model = model,
        tokenizer = tokenizer,
        train_dataset = dataset,
        dataset_text_field = "output",
        max_seq_length = MAX_SEQ_LENGTH,
        dataset_num_proc = 2,
        args = TrainingArguments(
            per_device_train_batch_size = 2,
            gradient_accumulation_steps = 4,
            warmup_steps = 5,
            max_steps = 60,
            learning_rate = 2e-4,
            fp16 = not torch.cuda.is_bf16_supported(),
            bf16 = torch.cuda.is_bf16_supported(),
            logging_steps = 1,
            output_dir = OUTPUT_DIR,
            optim = "adamw_8bit",
        ),
    )
    
    trainer.train()

    model.save_pretrained("autonomy_engine/brain/evolved_v1")
    print(">>> CEREBRAL UPDATE COMPLETE. NEW SYNAPSES FORMED. <<<")

if __name__ == "__main__":
    train_self()
