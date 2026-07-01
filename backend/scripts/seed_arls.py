"""Seed Fondos de Pensión — wrapper del script unificado.

DEPRECATED: Este archivo se mantiene por compatibilidad con scripts antiguos
que ejecutan `python -m scripts.seed_arls`. Ahora siembra Fondos de Pensión.

Uso recomendado:
    python -m scripts.seed pension-funds
"""
import warnings
from scripts.seed_pension_funds import main

if __name__ == "__main__":
    warnings.warn(
        "seed_arls está deprecado. Use 'python -m scripts.seed pension-funds'.",
        DeprecationWarning,
        stacklevel=2,
    )
    import asyncio
    asyncio.run(main())