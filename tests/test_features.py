import os
import sys
import pandas as pd
from ml.parse_logs import read_and_group_events
from ml.features import extract_all_features

def test_features():
    fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
    log_file = os.path.join(fixtures_dir, 'sample_cowrie.json')
    
    sessions, _, _ = read_and_group_events(log_file)
    features = extract_all_features(sessions)
    
    assert len(features) == 11
    
    # Check session s4 (command_attack)
    s4 = next(f for f in features if f['session_id'] == 's4')
    assert s4['n_commands'] == 2
    assert s4['n_suspicious_commands'] == 2 # wget and chmod +x
    
    # Check session s5 (incomplete)
    s5 = next(f for f in features if f['session_id'] == 's5')
    assert s5['session_incomplete'] == 1
    assert s5['n_commands'] == 1
    
    print("test_features passed!")
