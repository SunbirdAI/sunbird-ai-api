.PHONY: lint-apply lint-check

lint-check:
	@echo "Checking for lint errors..."
	flake8 .
	black --check .
	isort --check-only .

lint-apply:
	@echo "apply linting ..."
	black .
	isort .
