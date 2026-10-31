PYTHON ?= $(shell if [ -f /mnt/vault/Projects/R_and_D/.venv/bin/python ]; then echo "/mnt/vault/Projects/R_and_D/.venv/bin/python"; else echo "python3"; fi)

.PHONY: all data analysis charts doe test clean

all: data analysis charts doe test

data:
	$(PYTHON) src/generate_data.py

analysis:
	$(PYTHON) analysis.py

charts:
	$(PYTHON) src/charts.py

doe:
	$(PYTHON) doe/generate_doe.py
	$(PYTHON) doe/anova_analysis.py
	$(PYTHON) doe/plots.py

test:
	$(PYTHON) tests/selfcheck.py

clean:
	rm -rf out/*.csv out/*.json charts/*.png doe/*.csv doe/*.json data/*.csv data/*.db __pycache__ src/__pycache__ doe/__pycache__ tests/__pycache__
