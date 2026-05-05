FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
# --extra-index-url pulls CPU-only torch wheels (avoids torchvision/CUDA bloat)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# small lib requirements
COPY requirements-add.txt .
RUN pip install --no-cache-dir -r requirements-add.txt

# Copy entire project
COPY . .

# Expose Streamlit port
EXPOSE 8501

ENV PYTHONUNBUFFERED=1

# Run the orchestrator
CMD ["python", "sankalp_orchestrator.py"]
