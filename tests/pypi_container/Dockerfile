FROM python:3.11-slim

ARG PACKAGE_VERSION

RUN pip install --no-cache-dir "spotify-cmd==${PACKAGE_VERSION}"

COPY run_smoke.py /run_smoke.py

CMD ["python", "/run_smoke.py"]
