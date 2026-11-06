FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-eng libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/redactor
COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv==0.9.28 \
    && uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/opt/redactor/.venv/bin:$PATH" \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PYTHONUNBUFFERED=1

WORKDIR /work
COPY redactor.toml ./redactor.toml
ENTRYPOINT ["redactor"]
