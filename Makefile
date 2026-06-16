.PHONY: check test lint

check: lint test

lint:
	python3 -m compileall -q src tests

test:
	PYTHONPATH=src python3 -m unittest discover -s tests
