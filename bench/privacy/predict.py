"""Run one privacy model over the test set and write predictions (kinds per item, time).
Runs inside the gx11 evaluation container (bench/privacy/Dockerfile), CPU only.
Only labels that are personal data count; cities, organisations, plain dates, usernames
do not (a city alone does not identify anyone).
usage: python3 predict.py MODEL TESTSET OUT"""
import json, sys, time

THRESHOLD = 0.5
WINDOW, OVERLAP = 1500, 200   # characters; keeps every window under 512 tokens


def windows(text):
    i = 0
    while True:
        yield i, text[i:i + WINDOW]
        if i + WINDOW >= len(text): return
        i += WINDOW - OVERLAP


def presidio():
    from presidio_analyzer import AnalyzerEngine
    engine = AnalyzerEngine()
    keep = {'PERSON': 'name', 'PHONE_NUMBER': 'phone', 'EMAIL_ADDRESS': 'email', 'AU_TFN': 'tfn',
            'AU_MEDICARE': 'medicare', 'AU_ABN': 'abn', 'CREDIT_CARD': 'card', 'IBAN_CODE': 'bank'}
    def run(text):
        return {keep[r.entity_type] for r in engine.analyze(text=text, language='en', score_threshold=THRESHOLD) if r.entity_type in keep}
    return run, 'presidio-analyzer + spacy en_core_web_lg'


def gliner(name):
    from gliner import GLiNER
    model = GLiNER.from_pretrained(name)
    labels = {'person name': 'name', 'street address': 'address', 'date of birth': 'dob', 'phone number': 'phone',
              'email address': 'email', 'tax file number': 'tfn', 'medicare number': 'medicare',
              'bank account number': 'bank', 'credit card number': 'card', 'passport number': 'passport',
              'driver licence number': 'licence'}
    def run(text):
        return {labels[e['label']] for e in model.predict_entities(text, list(labels), threshold=THRESHOLD)}
    return run, name


def token_model(name, keep):
    from transformers import pipeline
    nlp = pipeline('token-classification', model=name, aggregation_strategy='simple', device=-1)
    def run(text):
        return {keep[e['entity_group']] for e in nlp(text) if e['entity_group'] in keep and e['score'] >= THRESHOLD}
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
    run, ident = MODELS[model]()
    items = [json.loads(l) for l in open(testset)]
    with open(out, 'w') as f:
        for item in items:
            start = time.perf_counter(); kinds = set()
            for _, chunk in windows(item['text']):
                kinds |= run(chunk)
            ms = (time.perf_counter() - start) * 1000
            f.write(json.dumps({'id': item['id'], 'kinds': sorted(kinds), 'ms': round(ms, 2), 'chars': len(item['text'])}) + '\n')
    print(model, ident, len(items), 'items ->', out)


if __name__ == '__main__':
    main()
