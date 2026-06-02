# Makefile — Language-Agnostic Subproject Template
#
# Adapt the commands below for your specific language/toolchain.
# Examples are shown in comments for Python (uv), Node.js (npm), and Rust (cargo).

.PHONY: install lint test coverage clean

# Install project dependencies
install:
	@echo "Replace this with your package manager:"
	@echo "  Python:  uv sync"
	@echo "  Node.js: npm install"
	@echo "  Rust:    cargo build"
	@echo "  Go:      go mod download"

# Run linter / static analysis
lint:
	@echo "Replace this with your linter:"
	@echo "  Python:  uv run ruff check ."
	@echo "  Node.js: npx eslint ."
	@echo "  Rust:    cargo clippy"
	@echo "  Go:      go vet ./..."

# Run tests
test:
	@echo "Replace this with your test runner:"
	@echo "  Python:  uv run pytest"
	@echo "  Node.js: npm test"
	@echo "  Rust:    cargo test"
	@echo "  Go:      go test ./..."

# Run tests with coverage report
coverage:
	@echo "Replace this with your coverage tool:"
	@echo "  Python:  uv run pytest --cov=<source_dir> --cov-report=html"
	@echo "  Node.js: npx jest --coverage"
	@echo "  Rust:    cargo tarpaulin"
	@echo "  Go:      go test -coverprofile=coverage.out ./..."

# Clean up build/test artifacts
clean:
	@echo "Replace this with your clean command:"
	@echo "  Python:  rm -rf .pytest_cache .coverage coverage.xml dist build *.egg-info __pycache__ .ruff_cache"
	@echo "  Node.js: rm -rf node_modules dist coverage .next"
	@echo "  Rust:    cargo clean"
	@echo "  Go:      go clean"
