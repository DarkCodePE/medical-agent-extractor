# Utilizar la imagen base de Python
FROM python:3.10

# Instala la dependencia libGL necesaria para OpenCV
RUN apt-get update && apt-get install -y libgl1-mesa-glx

# Establecer el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar el archivo de requisitos e instalar las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar solo los archivos necesarios de la aplicación
COPY main.py .
COPY .env .
COPY langgraph.json .
COPY app/ ./app/
# Comando para ejecutar la aplicación
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9002"]