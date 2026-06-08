FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port 7860 (Hugging Face Spaces default port)
EXPOSE 7860

# Run the simulator serving the web UI
CMD ["python", "-m", "simulator", "--scenario", "simulator/scenarios/simple_lan.json", "--port", "7860"]
