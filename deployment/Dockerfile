FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv/vaidya
RUN useradd --system --no-create-home --uid 10001 vaidya
COPY requirements.txt requirements-production.txt requirements-sarvam.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt
COPY production ./production
COPY vaidya ./vaidya
COPY production_app.py ./
COPY deployment/alembic ./deployment/alembic
COPY deployment/alembic.ini ./deployment/alembic.ini
USER 10001
EXPOSE 8080
CMD ["gunicorn","-w","2","--threads","4","-b","0.0.0.0:8080","--access-logfile","-","production_app:app"]
