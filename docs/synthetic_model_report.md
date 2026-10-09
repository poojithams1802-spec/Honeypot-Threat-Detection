# Model Report (SYNTHETIC)

**SYNTHETIC - pipeline test only, not valid results.**

## Dataset Statistics
- Train runs: 128
- Test runs: 32

## Metrics
### RandomForest
- Accuracy: 1.000
- Macro F1: 1.000
- Weighted F1: 1.000

### Dummy
- Accuracy: 0.242
- Macro F1: 0.097
- Weighted F1: 0.094

### DecisionTree
- Accuracy: 1.000
- Macro F1: 1.000
- Weighted F1: 1.000

### LogisticRegression
- Accuracy: 1.000
- Macro F1: 1.000
- Weighted F1: 1.000

Note: The model scored ~100%. This likely means the attack scenarios are too easy to tell apart (especially in synthetic data). To make it harder, you could add more noise, vary command sets more organically, or blend normal behavior with attack runs.

## Leakage Checks
- Dropping top 3 features (n_suspicious_commands, n_unique_commands, avg_command_length) resulted in a macro-F1 drop of 0.034.
- Sanity check: Training on shuffled labels gave macro-F1 of 0.193 (expected near chance).

## Error Analysis
Most common misclassifications (True -> Predicted):

Sample Misclassified Sessions (True -> Predicted):