import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download
from llama_cpp import Llama
import pandas as pd
from tqdm import tqdm


def generate_prompt_meta(df_type):

    def inner(row_dict):
        prompt = f"Review the following information about a {df_type}:\n"

        for key, value in row_dict.items():
            if key.lower() in ['url', 'image_urls']:
                continue
            prompt += f"{key}: {value}\n"

        prompt += f"""
        And its DuckDuckGo-sourced description:
        WikiDescription: {row_dict.get('WikiDescription', '[No Wiki Description]')} 
        
        Is the WikiDescription accurate and relevant to this {df_type}? Answer with 'Yes' or 'No' only."""

        return prompt.strip()
    return inner


def process_model_response(response):
    if response.strip().lower() == 'yes':
        return True
    elif response.strip().lower() == 'no':
        return False
    else:
        # Handle unexpected responses
        return None


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Validate WikiDescription fields against LLM judgment"
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory containing input CSVs (default: <script_dir>/data)",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Path to a GGUF model. If omitted, the model is downloaded via hf_hub_download",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=100,
        help="Write partial output every N records",
    )
    parser.add_argument(
        "--gpu-layers",
        type=int,
        default=None,
        help="Number of layers to offload to GPU. If omitted, llama.cpp default is used",
    )
    return parser


def resolve_data_dir(args):
    if args.data_dir is not None:
        return Path(args.data_dir)
    return Path(__file__).resolve().parent / "data"


def load_model(model_path_str, gpu_layers):
    model_kwargs = {"n_gqa": 8, "n_ctx": 8192}
    if gpu_layers is not None:
        model_kwargs["n_gpu_layers"] = gpu_layers
    return Llama(model_path=model_path_str, **model_kwargs)


def validate_file(data_dir, input_file, generate_prompt, output_file, model, checkpoint_every):
    df = pd.read_csv(data_dir / input_file)

    processed_count = 0

    for index, row in tqdm(df.iterrows(), total=df.shape[0]):
        prompt = generate_prompt(row.to_dict())
        response = model(prompt)['choices'][0]['text']
        processed_response = process_model_response(response)
        df.at[index, 'ValidatedRaw'] = response
        df.at[index, 'Validated'] = processed_response

        processed_count += 1
        if processed_count % checkpoint_every == 0:
            print(f"Processed {processed_count} records")
            df.to_csv(data_dir / output_file)

    df.to_csv(data_dir / output_file)
    # Avoid duplicating the checkpoint message when the total is an exact
    # multiple of checkpoint_every (e.g. 100 records with --checkpoint-every 100).
    if processed_count % checkpoint_every != 0:
        print(f"Processed {processed_count} records")
    return True


if __name__ == '__main__':
    args = build_argument_parser().parse_args()

    data_dir = resolve_data_dir(args)
    print(f"Data directory: {data_dir}")

    model_path = args.model_path or hf_hub_download(
        repo_id="TheBloke/Mistral-7B-Instruct-v0.1-GGUF",
        filename="mistral-7b-instruct-v0.1.Q8_0.gguf",
    )

    try:
        model = load_model(model_path, args.gpu_layers)
    except Exception as exc:
        print(f"Failed to load model {model_path}: {exc}")
        raise SystemExit(1)

    jobs = [
        ('data_update.csv', generate_prompt_meta("painting"), 'data_validated.csv'),
        ('artist_update.csv', generate_prompt_meta("artist"), 'artist_validated.csv'),
        ('movements_update.csv', generate_prompt_meta("art movement"), 'movement_validated.csv'),
        ('schools_update.csv', generate_prompt_meta("art school"), 'school_validated.csv'),
        ('styles_update.csv', generate_prompt_meta("art style"), 'styles_validated.csv'),
    ]

    for input_file, generate_prompt, output_file in jobs:
        try:
            validate_file(data_dir, input_file, generate_prompt, output_file, model, args.checkpoint_every)
        except Exception as exc:
            print(f"Failed to process {input_file}: {exc}")
