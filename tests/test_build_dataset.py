import os
import pandas as pd
from ml.build_dataset import build_dataset

def test_build_dataset(tmp_path):
    fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
    log_file = os.path.join(fixtures_dir, 'sample_cowrie.json')
    manifest_file = os.path.join(fixtures_dir, 'sample_manifest.csv')
    
    out_dir = tmp_path / "processed"
    report_file = tmp_path / "docs" / "dataset_report.md"
    
    build_dataset(log_file, manifest_file, str(out_dir), str(report_file))
    
    assert (out_dir / "sessions_features.csv").exists()
    assert (out_dir / "dataset.csv").exists()
    assert (out_dir / "dataset_meta.csv").exists()
    assert report_file.exists()
    
    df_dataset = pd.read_csv(out_dir / "dataset.csv")
    assert len(df_dataset) == 5
    
    assert list(df_dataset[df_dataset['run_id'] == 'r4']['label'])[0] == 'command_attack'
    assert list(df_dataset[df_dataset['run_id'] == 'r5']['label'])[0] == 'normal'
    
    print("test_build_dataset passed!")
