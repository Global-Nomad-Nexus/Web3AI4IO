PYTHON ?= $(firstword $(wildcard .venv/bin/python) python3)
REPO := $(abspath .)
PAPER := $(if $(wildcard paper/neurips_2026.tex),$(abspath paper),$(abspath ../paper))
export PYTHONPATH := $(REPO)/reproduction:$(PYTHONPATH)
export MPLCONFIGDIR := $(REPO)/reproduction/.mplconfig
WEB3AI4IO_PAPER_DIR ?= $(PAPER)
export WEB3AI4IO_PAPER_DIR

.PHONY: archive tables figures manifest verify identity tests reproduce paper all \
	agentic-v2-dry-run agentic-v2-smoke agentic-v2-run agentic-v2-score agentic-v2-verify \
	agentic-v2-all agentic-v2-configure agentic-v2-clear-credentials \
	telegram-audit-dry-run telegram-audit-run telegram-audit-score telegram-audit-verify \
	agentic-v2-matched

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

agentic-v2-dry-run:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/run_agentic_v2.py \
		--dry-run --conditions all --output-dir application/artifacts/agentic_v2/dry_run

agentic-v2-smoke:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/run_agentic_v2.py \
		--model-panel qwen3_14b --conditions canonical --runs-per-cell 1 \
		--max-cells 1 --timeout 900 --output-dir application/artifacts/agentic_v2/smoke

agentic-v2-run:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/run_agentic_v2.py \
		--conditions all --resume

agentic-v2-score:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/score_agentic_v2.py

agentic-v2-verify:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/verify_agentic_v2.py

agentic-v2-all:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/run_agentic_v2_all.py

agentic-v2-configure:
	$(PYTHON) application/scripts/configure_agentic_v2_keychain.py \
		--openai-base-url "$(OPENAI_BASE_URL)"

agentic-v2-clear-credentials:
	$(PYTHON) application/scripts/configure_agentic_v2_keychain.py --delete

agentic-v2-matched:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/reanalyze_agentic_v2_matched.py

telegram-audit-dry-run:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/run_telegram_replication.py \
		--dry-run --output-dir application/artifacts/telegram_replication/dry_run

telegram-audit-run:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/run_telegram_replication.py --resume

telegram-audit-score:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/score_telegram_replication.py

telegram-audit-verify:
	PYTHONPATH=$(REPO)/application/src $(PYTHON) application/scripts/verify_telegram_replication.py
