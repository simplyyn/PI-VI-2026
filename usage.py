"""Only provider-reported counts. No prompts, responses, keys, or quota guesses."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.Lock()


def path():
    return Path(os.getenv('SMARTDENT_USAGE_PATH', 'data/llm-usage.jsonl'))


def record_usage(clinic, provider, model, counts, attempts):
    if clinic is None:
        return
    clean = {name: value if type(value) is int and value >= 0 else None for name, value in counts.items()}
    row = dict(clinic=clinic, provider=provider, model=model, timestamp=datetime.now(timezone.utc).isoformat(), attempts=attempts, **clean)
    try:
        with _lock:
            target = path()
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=True) + '\n')
    except OSError:
        # Usage telemetry must never turn a successful answer into an error.
        import logging
        logging.getLogger(__name__).warning('Não foi possível registrar métricas de consumo da LLM.')


def totals(clinic):
    result = dict(chamadas_registradas=0, chamadas_sem_contagem=0, tokens_entrada=0, tokens_saida=0, tokens_total_informado=0, tokens_raciocinio_informado=0,
                  escopo='Chamadas registradas por esta aplicação para sua clínica. Não é a cota ou o faturamento do provedor.')
    try:
        with _lock, path().open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if row.get('clinic') != clinic: continue
                    result['chamadas_registradas'] += 1
                    if row.get('input') is None or row.get('output') is None: result['chamadas_sem_contagem'] += 1
                    for key, target in [('input','tokens_entrada'),('output','tokens_saida'),('total','tokens_total_informado'),('thinking','tokens_raciocinio_informado')]:
                        value = row.get(key)
                        if type(value) is int and value >= 0: result[target] += value
                except (ValueError, TypeError, AttributeError):
                    continue
    except FileNotFoundError:
        pass
    return result
