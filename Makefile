# Every target here is what CI runs. `make verify` is the whole gate.
.DEFAULT_GOAL := help
.PHONY: help sync fmt fmt-check lint typecheck security audit test no-dashes verify clean

UV ?= uv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

sync: ## Install the locked dependency set
	$(UV) sync --locked

fmt: ## Format the code
	$(UV) run ruff format .

fmt-check: ## Check formatting without changing anything
	$(UV) run ruff format --check .

lint: ## Lint
	$(UV) run ruff check .

typecheck: ## Type check
	$(UV) run mypy

security: ## Static security scan of the package
	$(UV) run bandit -q -c pyproject.toml -r src

audit: ## Audit locked dependencies for known vulnerabilities (needs network)
	@NO_COLOR=1 $(UV) export --locked --no-emit-project --no-header --no-hashes \
	  --no-annotate --format requirements-txt > requirements-audit.txt
	$(UV) run pip-audit --strict -r requirements-audit.txt
	@rm -f requirements-audit.txt

test: ## Run the tests with the coverage floor
	$(UV) run pytest

no-dashes: ## Reject em dashes and en dashes in tracked text
# `git grep` exits 0 when it matches, 1 when it does not, and 128 when it
# could not look: a malformed pattern, no repository, an unreadable object.
# Folding 128 into the "no match" branch is how a gate announces success for
# having failed to run, which is what the byte-escape spelling of this pattern
# did for the whole life of the repository. The three outcomes are kept apart.
# No `set -e` here on purpose: it would abort on the grep's own non-zero exit
# before the status could be read, and "no match" is a non-zero exit.
	@out=$$(git grep -n -P '\x{2013}|\x{2014}' -- ':!*.lock' ':!uv.lock' 2>&1); \
	status=$$?; \
	if [ $$status -eq 0 ]; then \
	  echo "Found em/en dashes in tracked files:"; echo "$$out"; exit 1; \
	elif [ $$status -eq 1 ]; then \
	  echo "no em/en dashes"; \
	else \
	  echo "the dash gate could not run (git grep exited $$status):"; \
	  echo "$$out"; \
	  echo "Refusing to report success for a check that did not happen."; \
	  exit $$status; \
	fi

verify: fmt-check lint typecheck security test no-dashes ## Run the full gate
	@echo "verify OK"

clean: ## Remove build and test artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
