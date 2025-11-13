SCRIPT1 := curzon-listings.sh
SCRIPT2 := import_showtimes.py
SCRIPT3 := capture_curzon_headless.js
TARGET_DIR := /var/www/ianmiell.com/curzon-listings
OWNER := www-data
DBFILE:= curzon-showtimes.db
TARGET1 := $(TARGET_DIR)/$(SCRIPT1)
TARGET2 := $(TARGET_DIR)/$(SCRIPT2)
TARGET3 := $(TARGET_DIR)/$(SCRIPT3)
WWW_DATA_HOME := /var/www

.PHONY: install clean run
install: $(SCRIPT)
	sudo install -Dm755 $(SCRIPT1) $(TARGET1)
	sudo install -Dm755 $(SCRIPT2) $(TARGET2)
	sudo install -Dm755 $(SCRIPT3) $(TARGET3)
	sudo cp -r node_modules $(TARGET_DIR)
	sudo mkdir -p $(WWW_DATA_HOME)/.cache
	sudo cp -r ~/.cache/puppeteer $(WWW_DATA_HOME)/.cache
	sudo cp package* $(TARGET_DIR)
	sudo chown -R www-data: $(TARGET_DIR)
	sudo chown -R www-data: $(WWW_DATA_HOME)/.cache

clean:
	rm -f $(DBFILE)

run:
	curzon-listings.sh
