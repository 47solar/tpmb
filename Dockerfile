FROM python:3.11-slim

# Create nonroot user
RUN useradd -m "your system username without quotese"
WORKDIR .

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
RUN chown -R "your system username without quotese":"your system username without quotese" .

USER "your system username without quotese"
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
