DB ?= rooms
MODULE := room_reservation
ODOO_BRANCH := 19.0

.PHONY: up down logs install upgrade test fresh lint dev-init

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f odoo

install:
	docker compose run --rm odoo odoo -d $(DB) -i $(MODULE) --stop-after-init --without-demo

upgrade:
	docker compose run --rm odoo odoo -d $(DB) -u $(MODULE) --stop-after-init

test:
	docker compose run --rm odoo odoo -d $(DB) -u $(MODULE) \
		--test-enable --test-tags /$(MODULE) --stop-after-init

fresh:
	docker compose down -v
	$(MAKE) install
	$(MAKE) up

lint:
	ruff check $(MODULE)

dev-init:
	# Shallow clone: the sources are only needed so the language server can
	# resolve "from odoo import ...". Odoo is not published on PyPI, and the
	# checkout is referenced through extraPaths in pyrightconfig.json rather
	# than installed, because a PEP 660 editable install registers an import
	# hook that a static language server cannot follow.
	test -d .odoo-src || git clone --depth 1 --branch $(ODOO_BRANCH) \
		https://github.com/odoo/odoo.git .odoo-src
