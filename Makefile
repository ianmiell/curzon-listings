PORT ?= 6752
UNIT := curzon_listings.service

.PHONY: venv run scrape check install restart status logs

venv: venv/bin/gunicorn

venv/bin/gunicorn: requirements.txt
	python3 -m venv venv
	venv/bin/pip install -q -r requirements.txt
	touch $@

# Flask dev server on 127.0.0.1:5000
run: venv
	venv/bin/flask --app app run

# Scrape once and print the JSON (takes about a minute)
scrape: venv
	venv/bin/python curzon.py > /dev/null

check: venv
	venv/bin/python -m py_compile app.py curzon.py
	bash -n cat_listings.sh
	venv/bin/python -c 'import app; c = app.app.test_client(); print(*(c.get(u).status_code for u in ("/", "/?when=all&by=cinema", "/listings.txt", "/health")))'

install: venv
	sudo install -m 644 deploy/$(UNIT) /etc/systemd/system/$(UNIT)
	sudo systemctl daemon-reload
	sudo systemctl enable --now $(UNIT)

restart:
	sudo systemctl restart $(UNIT)

status:
	systemctl status --no-pager $(UNIT) || true
	curl -fsS http://127.0.0.1:$(PORT)/health; echo

logs:
	journalctl -u $(UNIT) -n 100 --no-pager
