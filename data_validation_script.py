import argparse
import sqlite3

import pandas as pd

from ScrapWikiArt import db
from ScrapWikiArt.settings import WIKIART_DB_PATH

# Fallback used when the setting is absent (keep in sync with settings.py).
DEFAULT_DB_PATH = WIKIART_DB_PATH

# Keys never included in LLM prompts: pipeline-only fields and DB bookkeeping.
_PROMPT_SKIP_KEYS = frozenset(["url", "image_urls", "scraped_at", "validatedraw", "validated"])


def generate_prompt_meta(df_type):

    def inner(row_dict):
        prompt = f"Review the following information about a {df_type}:\n"

        for key, value in row_dict.items():
            if key.lower() in _PROMPT_SKIP_KEYS:
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
        "--db-path",
        default=None,
        help=f"Path to the SQLite database (default: {DEFAULT_DB_PATH})",
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


def resolve_db_path(args):
    """Resolve the DB path: explicit --db-path wins, else the settings default."""
    if args.db_path is not None:
        return args.db_path
    return DEFAULT_DB_PATH


def load_works(conn):
    """Read every works row for validation (DV.2/DV.4: single-pass replace of
    the old 5-file CSV jobs list)."""
    return pd.read_sql("SELECT * FROM works", conn)


def _validated_to_db(v):
    """Coerce the boolean Validated flag into a stable text value.

    The works.Validated column is TEXT: raw bools would be stored as '1'/'0'
    via SQLite's TEXT affinity, diverging from the old CSV output ("True"/"False").
    None stays NULL (unparseable model response).
    """
    if v is True:
        return "True"
    if v is False:
        return "False"
    return None


def write_validation(conn, df):
    """Persist ValidatedRaw/Validated back to the works table.

    executemany UPDATE per checkpoint + final (design D6). Deliberately NOT
    df.to_sql(): to_sql(if_exists='replace') recreates the table and drops the
    Id PRIMARY KEY, breaking future INSERT OR IGNORE dedup; append would
    duplicate rows. Spec DV.3 intent (columns persisted) is met.
    """
    rows = [
        (row.ValidatedRaw, _validated_to_db(row.Validated), row.Id)
        for row in df[["ValidatedRaw", "Validated", "Id"]].itertuples(index=False)
    ]
    if not rows:
        return
    conn.executemany(
        "UPDATE works SET ValidatedRaw = ?, Validated = ? WHERE Id = ?",
        rows,
    )
    conn.commit()


def load_model(model_path_str, gpu_layers):
    from llama_cpp import Llama  # lazy: heavy native dependency

    model_kwargs = {"n_gqa": 8, "n_ctx": 8192}
    if gpu_layers is not None:
        model_kwargs["n_gpu_layers"] = gpu_layers
    return Llama(model_path=model_path_str, **model_kwargs)


def validate_works(conn, generate_prompt, model, checkpoint_every):
    from tqdm import tqdm  # lazy: not needed for tests

    df = load_works(conn)

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
            write_validation(conn, df)

    write_validation(conn, df)
    # Avoid duplicating the checkpoint message when the total is an exact
    # multiple of checkpoint_every (e.g. 100 records with --checkpoint-every 100).
    if processed_count % checkpoint_every != 0:
        print(f"Processed {processed_count} records")
    return True


if __name__ == '__main__':
    from huggingface_hub import hf_hub_download  # lazy: heavy dependency

    args = build_argument_parser().parse_args()

    db_path = resolve_db_path(args)
    print(f"Database: {db_path}")

    model_path = args.model_path or hf_hub_download(
        repo_id="TheBloke/Mistral-7B-Instruct-v0.1-GGUF",
        filename="mistral-7b-instruct-v0.1.Q8_0.gguf",
    )

    try:
        model = load_model(model_path, args.gpu_layers)
    except Exception as exc:
        print(f"Failed to load model {model_path}: {exc}")
        raise SystemExit(1)

    with sqlite3.connect(db_path) as conn:
        # Uses default isolation (not db.connect's autocommit) because
        # executemany UPDATE batches are wrapped in a single transaction
        # for atomicity (one commit per checkpoint).  Same WAL/busy_timeout
        # pragmas as db.connect for safe concurrent access.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        validate_works(conn, generate_prompt_meta("painting"), model, args.checkpoint_every)
