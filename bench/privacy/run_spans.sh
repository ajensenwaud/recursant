#!/bin/sh
# Span predictions for the privacy detectors on gx11 (one 8-core, 3 GB container at a time,
# so the GLM worker sharing the machine keeps its memory and most of its CPU).
# Sets: testset (design), synth-holdout and holdout (held out).
# Pass 1 (whole texts): bert-ner fp32 and int8, presidio, on all sets.
#   int8 is only scored on the design set: no faster on gx11 (380 vs 355 ms per 1,000
#   chars) and it cost Piiranha most of its name recall (71% -> 20%).
# Pass 2 (GATE=1, this script): the model reads only gated lines; time is the real cost.
cd ~/recursant-privacy || exit 1
run() {  # model set
  docker run --rm --cpus=8 --memory=3g -e GATE=1 -e HF_HUB_OFFLINE=1 -v $PWD/models:/models -v $PWD/data:/data \
    -v $PWD/out:/out -v $PWD/predict.py:/eval/predict.py -v $PWD/filters.py:/eval/filters.py recursant-privacy-eval:latest \
    $1 /data/$2.jsonl /out/span-$1-g1-$2.jsonl 2>&1 | grep -v -i warning | tail -1
}
for m in presidio bert-ner piiranha; do
  for set in testset synth-holdout holdout; do run $m $set; done
done
echo ALL DONE
