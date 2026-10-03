"""Phase 5 offline check: does a small local encoder predict which questions need worked
answers better than the router's bag-of-words classifier (AUC 0.62-0.64)?

Runs inside recursant-privacy-eval (torch + transformers, CPU) on gx11. For each encoder:
mean-pooled (or the model's own pooling) normalized embeddings of each question, then an
L2 logistic regression head (LBFGS), out-of-fold scores for 5-fold (seeded, same split as
bench/prompt/reasoning_switch.py is not required: scores are evaluated by that script) and
leave-one-subject-out. Writes {model: {"kfold": [...], "loso": [...], "secs_per_q": x}}.
usage: python3 embed_eval.py ITEMS.jsonl CHEAP.graded.jsonl EXPENSIVE.graded.jsonl OUT.json MODEL [MODEL...]"""
import json, random, sys, time
import torch
from transformers import AutoModel, AutoTokenizer

torch.set_num_threads(8)
items = [json.loads(l) for l in open(sys.argv[1])]
cheap = {json.loads(l)['id']: json.loads(l)['correct'] for l in open(sys.argv[2])}
dear = {json.loads(l)['id']: json.loads(l)['correct'] for l in open(sys.argv[3])}
items = [x for x in items if x['id'] in cheap and x['id'] in dear]
y = torch.tensor([1.0 if dear[x['id']] and not cheap[x['id']] else 0.0 for x in items])
subjects = [x.get('subject', '') for x in items]


def embed(name):
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModel.from_pretrained(name, torch_dtype=torch.float32).eval()
    out = []; start = time.time()
    with torch.no_grad():
        for i in range(0, len(items), 16):
            batch = tok([x['question'] for x in items[i:i + 16]], padding=True, truncation=True, max_length=512, return_tensors='pt')
            h = model(**batch).last_hidden_state
            if 'qwen' in name.lower():   # last-token pooling (left padding not assumed: take last real token)
                idx = batch['attention_mask'].sum(1) - 1
                e = h[torch.arange(h.size(0)), idx]
            elif 'bge' in name.lower():  # CLS pooling
                e = h[:, 0]
            else:                        # mean pooling
                m = batch['attention_mask'].unsqueeze(-1).float(); e = (h * m).sum(1) / m.sum(1)
            out.append(torch.nn.functional.normalize(e, dim=-1))
    return torch.cat(out), (time.time() - start) / len(items)


def fit_predict(X, y, train, test, l2=1e-2):
    w = torch.zeros(X.size(1), requires_grad=True); b = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=200, line_search_fn='strong_wolfe')
    Xt, yt = X[train], y[train]
    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(Xt @ w + b, yt) + l2 * (w * w).sum()
        loss.backward(); return loss
    opt.step(closure)
    with torch.no_grad(): return torch.sigmoid(X[test] @ w + b)


def main():
    res = {}
    for name in sys.argv[5:]:
        X, secs = embed(name)
        X = X * 8.0   # scale so a modest l2 does not flatten unit-norm features
        n = len(items); idx = list(range(n)); random.Random(7).shuffle(idx)
        kfold = [0.0] * n
        for f in range(5):
            test = idx[f::5]; train = [i for i in range(n) if i not in set(test)]
            for i, p in zip(test, fit_predict(X, y, train, test).tolist()): kfold[i] = p
        loso = [0.0] * n
        for s in sorted(set(subjects)):
            test = [i for i in range(n) if subjects[i] == s]; train = [i for i in range(n) if subjects[i] != s]
            for i, p in zip(test, fit_predict(X, y, train, test).tolist()): loso[i] = p
        res[name] = {'ids': [x['id'] for x in items], 'kfold': kfold, 'loso': loso, 'secs_per_q': secs}
        print(name, 'embedded in %.1f ms per question (CPU, 8 threads)' % (1000 * secs), flush=True)
        json.dump(res, open(sys.argv[4], 'w'))


if __name__ == '__main__':
    main()
