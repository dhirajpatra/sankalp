FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire project
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Set environment variables with defaults
ENV PYTHONUNBUFFERED=1
ENV NEO4J_URI=bolt://neo4j:7687
ENV NEO4J_USER=${NEO4J_USER}
ENV NEO4J_PASSWORD=${NEO4J_PASSWORD}

# Run the orchestrator
CMD ["python", "sankalp_orchestrator.py"]
