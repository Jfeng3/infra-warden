.PHONY: check test lint build-e2b-template smoke-e2b run-task

check: lint test

lint:
	python3 -m compileall -q src tests

test:
	PYTHONPATH=src python3 -m unittest discover -s tests

build-e2b-template:
	python3 scripts/build_e2b_template.py

smoke-e2b:
	python3 -m warden_sandbox_infra smoke-e2b

run-task:
	test -n "$(TASK_ID)" || (echo "TASK_ID is required" >&2; exit 2)
	python3 scripts/run_warden_task.py --task-id "$(TASK_ID)"
