PYTHON ?= $(firstword $(wildcard .venv/bin/python) python3)
REPO := $(abspath .)
PAPER := $(if $(wildcard paper/neurips_2026.tex),$(abspath paper),$(abspath ../paper))
export PYTHONPATH := $(REPO)/reproduction:$(PYTHONPATH)
export MPLCONFIGDIR := $(REPO)/reproduction/.mplconfig

.PHONY: archive tables figures manifest verify identity tests reproduce paper all

archive:
	$(PYTHON) reproduction/archive_summaries.py

tables: archive
	$(PYTHON) reproduction/generate_tables.py

figures: archive
	$(PYTHON) reproduction/generate_figures.py

manifest: archive tables
	$(PYTHON) reproduction/generate_manifest.py

identity:
	$(PYTHON) reproduction/identity_audit.py

tests: archive
	$(PYTHON) -m pytest -q reproduction/tests

verify: archive tables manifest
	$(PYTHON) reproduction/verify.py
	$(PYTHON) reproduction/identity_audit.py
	$(PYTHON) -m pytest -q reproduction/tests

reproduce: archive tables figures manifest verify

paper:
	cd $(PAPER) && latexmk -pdf -interaction=nonstopmode neurips_2026.tex

all: reproduce paper
