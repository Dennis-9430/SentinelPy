# Dockerfile para el backend de SentinelPy
# Usa la imagen oficial slim de Python 3.13 para mantener el tamaño reducido

FROM python:3.13-slim

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Primero copiar requirements.txt para aprovechar cache de Docker
# (solo se reinstala si cambia requirements.txt, no si cambia el código)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código fuente
COPY . .

# Puerto que expone la aplicación
EXPOSE 8000

# Comando por defecto — se puede sobreescribir en docker-compose.yml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
