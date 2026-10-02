# Privacy model evaluation on gx11 (aarch64), CPU only. Run with a hard memory cap so the
# GLM worker sharing the machine can never be starved:  docker run --memory=3g ...
FROM python:3.12-slim
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir transformers==4.* gliner presidio-analyzer && \
    python -m spacy download en_core_web_lg
ENV HF_HOME=/models
WORKDIR /eval
COPY predict.py /eval/predict.py
ENTRYPOINT ["python3", "/eval/predict.py"]
