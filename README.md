# SOIC — Tool-verified Quality Gate Engine

**Version** : 3.1.0 (source de vérité : fichier `VERSION` à la racine)
**Statut** : production-ready, utilisé par NEXOS + OSIRIS

## Installation

```bash
pip install -e .
```

## Consumers

- **NEXOS** (`AILabManager-tech/nexos`) — pipeline de fabrication de sites
- **OSIRIS** (`AILabManager-tech/osiris-scanner`) — scanner sobriété/sécurité

## Architecture

- `soic/gate_engine.py` — orchestrateur principal
- `soic/converger.py` — convergence multi-dimension avec ENRICHED_RETRY
- `soic/iterator.py` — PhaseIterator/SOICIterator avec phase-specific timeouts
- `soic/domain_grids/` — grilles par domaine (code, web, prose, prompt, infra)
- `soic/feedback_router.py` — routage feedback vers prompts LLM
- `soic/persistence.py` — RunStore (soic-runs.jsonl + soic-gates.json)

## Tests

```bash
pytest tests/
```
