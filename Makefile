# Physical device automation. Existing component builds remain in build/.
PYTHON ?= automation/.venv/bin/python
AUTOMATION = $(PYTHON) -m automation.controller.cli
.PHONY: automation-setup automation-server automation-test device-check device-build device-install device-smoke-test jit-test

automation-setup:
	python3 -m venv automation/.venv
	automation/.venv/bin/python -m pip install -r automation/requirements.txt
	npm ci --prefix automation

automation-server:
	cd automation && npm run server

automation-test:
	$(PYTHON) -m pytest -q automation/tests

device-check:
	$(AUTOMATION) device-check

device-build:
	$(AUTOMATION) build $(BUILD_FLAGS)

device-install:
	@test -n "$(APP)" || (echo 'Set APP to a signed .app directory' >&2; exit 2)
	$(AUTOMATION) install "$(APP)"

device-smoke-test:
	$(AUTOMATION) smoke

jit-test:
	$(AUTOMATION) jit-test
