.PHONY: install run test lint samples
install:
	pip install -e ".[dev]"
run:
	uvicorn app.web.main:app --host 0.0.0.0 --port 8000 --reload
test:
	pytest -q
lint:
	ruff check .
samples:
	python samples/make_samples.py
