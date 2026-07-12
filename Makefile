.PHONY: check test lint build-e2b-template smoke-e2b

check: lint test

lint:
	python3 -m compileall -q src tests

test:
	PYTHONPATH=src python3 -m unittest discover -s tests

build-e2b-template:
	python3 scripts/build_e2b_template.py

smoke-e2b:
	python3 -m warden_sandbox_infra smoke-e2b
