# Console d'administration de la messagerie
FROM python:3.13.5-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Utilisateur sans privilège ; /donnees contient le journal d'audit et le jeton Synapse
RUN useradd --system --uid 10001 console && mkdir /donnees && chown console /donnees
USER console
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
