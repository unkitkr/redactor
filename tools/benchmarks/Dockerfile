FROM redactor:local
RUN uv pip install --python /opt/redactor/.venv/bin/python \
    onnxruntime==1.31.1 tokenizers==0.23.3 rapidocr==3.10.0
ENV TOKENIZERS_PARALLELISM=false HF_HUB_OFFLINE=1
ENTRYPOINT ["python"]
