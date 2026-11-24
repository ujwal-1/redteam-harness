# Red-team report

- Backend: `openai-compat` model: `llama3.2:3b`
- Defense: `spotlight+policy`
- Base attacks: 21, mutators: identity, trials: 3
- Total runs: 63

**Overall attack success rate: 0.0%** (0 of 63 runs). The model was fooled (attempted) in 20.6% of runs; the gap between attempted and succeeded is what the defenses stopped.

| Category | Runs | Succeeded | Attempted | Attack success rate |
|---|---|---|---|---|
| direct_injection | 18 | 0 | 0 | 0.0% |
| exfiltration | 15 | 0 | 12 | 0.0% |
| filter_evasion | 12 | 0 | 0 | 0.0% |
| indirect_injection | 18 | 0 | 1 | 0.0% |

| Mutator | Runs | Succeeded | Attempted | Attack success rate |
|---|---|---|---|---|
| identity | 63 | 0 | 13 | 0.0% |

## Successful attacks (examples)

None.