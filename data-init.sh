#!/bin/bash
# Data initialization script
# Creates SQLite tables from CSV files in data/raw/

set -e

echo "🛡️  SANKALP Data Initialization"
echo "==============================="

if [ ! -d "data/raw" ]; then
    echo "❌ Error: data/raw directory not found"
    exit 1
fi

if [ ! -f "agents/ganana.py" ]; then
    echo "❌ Error: agents/ganana.py not found"
    exit 1
fi

echo ""
echo "🔵 Checking CSV files..."
for file in data/raw/{aircraft,crew,missions}.csv; do
    if [ -f "$file" ]; then
        rows=$(tail -n +2 "$file" | wc -l)
        echo "  ✅ $(basename $file): $rows rows"
    else
        echo "  ⚠️  Missing: $(basename $file)"
    fi
done

echo ""
echo "🔵 Running Ganana (Ingestion)..."
python agents/ganana.py

echo ""
echo "🔵 Running Shodhan (Transformation)..."
python agents/shodhan.py

echo ""
echo "✅ Data initialization complete!"
echo ""
echo "📊 Database files created:"
echo "  - sankalp_raw.db   (raw data)"
echo "  - sankalp_gold.db  (transformed data)"
echo ""
