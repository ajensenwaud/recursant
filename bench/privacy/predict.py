"""Run one privacy model over the test set and write predictions (kinds per item, entity
spans, time). Runs inside the gx11 evaluation container (bench/privacy/Dockerfile), CPU only.
Only labels that are personal data count; cities, organisations, plain dates, usernames
do not (a city alone does not identify anyone).

Entity spans (text included) let the false-alarm filters in bench/privacy/filters.py be
scored offline without rerunning the model. The output holds test-set text, so it stays in
.hermes/runtime/privacy (never committed).

Options (environment):
  THREADS=n   torch threads (default: the container's CPU quota; torch otherwise starts one
              thread per host core, which oversubscribes a --cpus capped container)
  INT8=1      dynamic int8 quantisation of the Linear layers (no extra packages)
  LIMIT=n     only the first n items (timing runs)
  GATE=1      read only the lines bench/privacy/filters.gate passes (filters.py mounted at
              /eval/filters.py); time then measures the gated cost
usage: python3 predict.py MODEL TESTSET OUT"""
import json, os, sys, time

THRESHOLD = 0.5
WINDOW, OVERLAP = 1500, 200   # characters; keeps every window under 512 tokens


def windows(text):
    i = 0
    while True:
        yield i, text[i:i + WINDOW]
        if i + WINDOW >= len(text): return
        i += WINDOW - OVERLAP


def cpu_quota():
    try:
        quota, period = open('/sys/fs/cgroup/cpu.max').read().split()
        if quota != 'max': return max(1, int(int(quota) / int(period)))
    except OSError:
        pass
    return os.cpu_count()


def presidio():
    from presidio_analyzer import AnalyzerEngine
    engine = AnalyzerEngine()
    keep = {'PERSON': 'name', 'PHONE_NUMBER': 'phone', 'EMAIL_ADDRESS': 'email', 'AU_TFN': 'tfn',
            'AU_MEDICARE': 'medicare', 'AU_ABN': 'abn', 'CREDIT_CARD': 'card', 'IBAN_CODE': 'bank'}
    def run(text):
        return [(keep[r.entity_type], r.entity_type, r.score, r.start, r.end)
                for r in engine.analyze(text=text, language='en', score_threshold=THRESHOLD) if r.entity_type in keep]
    return run, 'presidio-analyzer + spacy en_core_web_lg'


def gliner(name):
    from gliner import GLiNER
    model = GLiNER.from_pretrained(name)
    labels = {'person name': 'name', 'street address': 'address', 'date of birth': 'dob', 'phone number': 'phone',
              'email address': 'email', 'tax file number': 'tfn', 'medicare number': 'medicare',
              'bank account number': 'bank', 'credit card number': 'card', 'passport number': 'passport',
              'driver licence number': 'licence'}
    def run(text):
        return [(labels[e['label']], e['label'], e['score'], e['start'], e['end'])
                for e in model.predict_entities(text, list(labels), threshold=THRESHOLD)]
    return run, name


def token_model(name, keep):
    import torch
    from transformers import pipeline
    nlp = pipeline('token-classification', model=name, aggregation_strategy='simple', device=-1)
    if os.environ.get('INT8') == '1':
        torch.backends.quantized.engine = 'qnnpack'
        nlp.model = torch.ao.quantization.quantize_dynamic(nlp.model, {torch.nn.Linear}, dtype=torch.qint8)
        name += ' (int8)'
    def run(text):
        return [(keep[e['entity_group']], e['entity_group'], float(e['score']), int(e['start']), int(e['end']))
                for e in nlp(text) if e['entity_group'] in keep and e['score'] >= THRESHOLD]
    return run, name


PIIRANHA = {'GIVENNAME': 'name', 'SURNAME': 'name', 'STREET': 'address', 'BUILDINGNUM': 'address',
            'DATEOFBIRTH': 'dob', 'TELEPHONENUM': 'phone', 'EMAIL': 'email', 'TAXNUM': 'tfn',
            'CREDITCARDNUMBER': 'card', 'ACCOUNTNUM': 'bank', 'DRIVERLICENSENUM': 'licence',
            'IDCARDNUM': 'medicare', 'SOCIALNUM': 'medicare'}
MODELS = {
    'presidio': presidio,
    'gliner-pii': lambda: gliner('urchade/gliner_multi_pii-v1'),
    'piiranha': lambda: token_model('iiiorg/piiranha-v1-detect-personal-information', PIIRANHA),
    'bert-ner': lambda: token_model('dslim/bert-base-NER', {'PER': 'name'}),
}


def main():
    model, testset, out = sys.argv[1:4]
    threads = int(os.environ.get('THREADS') or cpu_quota())
    try:
        import torch
        torch.set_num_threads(threads)
    except ImportError:
        pass
    run, ident = MODELS[model]()
    items = [json.loads(l) for l in open(testset)]
    if os.environ.get('LIMIT'): items = items[:int(os.environ['LIMIT'])]
    run('warm up the model before timing')
    gate = None
    if os.environ.get('GATE') == '1':   # read only the lines bench/privacy/filters.gate passes
        sys.path.insert(0, '/eval'); from filters import gate
    with open(out, 'w') as f:
        for item in items:
            start = time.perf_counter(); ents = []
            text = item['text']
            for gs, ge in (gate(text) if gate else [(0, len(text))]):
                for off, chunk in windows(text[gs:ge]):
                    for kind, label, score, s, e in run(chunk):
                        ents.append({'kind': kind, 'label': label, 'score': round(score, 3), 'start': gs + off + s,
                                     'end': gs + off + e, 'text': chunk[s:e]})
            ms = (time.perf_counter() - start) * 1000
            f.write(json.dumps({'id': item['id'], 'kinds': sorted({x['kind'] for x in ents}), 'ms': round(ms, 2),
                                'chars': len(item['text']), 'ents': ents}) + '\n')
    print(model, ident, 'threads', threads, len(items), 'items ->', out)


if __name__ == '__main__':
    main()
