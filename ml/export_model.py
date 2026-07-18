"""Export the registry's production model into the repo as a deployment
bundle (models/production/) — the MLflow registry lives in local sqlite
which GitHub Actions can't reach, so promotion = register + export +
commit. train.py calls this automatically after registering a winner.

Usage (repo root):  python ml/export_model.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

BUNDLE_DIR = common.ROOT / "models" / "production"


def export():
    mlflow = common.mlflow_setup()
    from mlflow import MlflowClient
    client = MlflowClient()
    mv = client.get_model_version_by_alias(common.MODEL_NAME, "production")
    loaded = mlflow.pyfunc.load_model(f"models:/{common.MODEL_NAME}@production")
    hit_model = loaded.unwrap_python_model().hit_model

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(hit_model, BUNDLE_DIR / "hit_model.joblib")
    (BUNDLE_DIR / "meta.json").write_text(json.dumps({
        "model_name": common.MODEL_NAME,
        "version": mv.version,
        "kind": hit_model.kind,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    print(f"exported {common.MODEL_NAME} v{mv.version} ({hit_model.kind}) "
          f"-> {BUNDLE_DIR}")


if __name__ == "__main__":
    export()
