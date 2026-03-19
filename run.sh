#!/bin/bash
#SBATCH -p q-3090
#SBATCH --gres=gpu:1
#SBATCH -t 12:00:00

# export MODEL_NAME="Qwen/Qwen3-14B-AWQ"
export MODEL_NAME="qwen/Qwen3-4B"
export BASE_URL="http://localhost:8000/v1"
export DATASET_NAME="medqa"

vllm serve "$MODEL_NAME" --port 8000 &
VLLM_PID=$!

trap "kill $VLLM_PID 2>/dev/null" EXIT

until curl -s http://localhost:8000/v1/models > /dev/null; do
    echo "Waiting for vLLM server..."
    sleep 5
done
srun python src/evaluate.py --llm_name "$MODEL_NAME" --dataset_name "$DATASET_NAME" --agents