PYTHON ?= $(shell if [ -f /mnt/vault/Projects/R_and_D/.venv/bin/python ]; then echo "/mnt/vault/Projects/R_and_D/.venv/bin/python"; else echo "python3"; fi)

.PHONY: all data analysis charts test clean

all: data analysis charts test

data:
	$(PYTHON) src/generate_data.py

analysis:
	$(PYTHON) analysis.py

charts:
	$(PYTHON) src/charts.py

test:
	$(PYTHON) tests/selfcheck.py

clean:
	rm -rf out/*.csv out/*.json charts/*.png data/*.csv data/*.db __pycache__ src/__pycache__ tests/__pycache__
