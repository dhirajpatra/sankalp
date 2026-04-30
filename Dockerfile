FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install big lib dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
