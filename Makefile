.PHONY: init test lint clean help

help:
	@echo "Homunculus Development Commands"
	@echo "================================"
	@echo "make init    - Initialize database"
	@echo "make test    - Run all tests"
	@echo "make lint    - Check Python syntax"
	@echo "make clean   - Remove runtime artifacts"
	@echo "make status  - Show system status"

init:
	python3 scripts/cli.py init

test:
	python3 -m unittest discover tests/ -v

lint:
	python3 -m py_compile scripts/*.py
	@echo "Syntax check passed"

clean:
	rm -f homunculus.db
	rm -f observations/current.jsonl
	rm -f logs/observations.log
	rm -f .current_session
	rm -rf scripts/__pycache__
	rm -rf tests/__pycache__
	@echo "Cleaned runtime artifacts"

status:
	python3 scripts/cli.py status
