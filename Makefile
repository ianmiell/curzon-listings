SCRIPT := curzon-listings.sh
TARGET_DIR := /var/www/ianmiell.com/curzon-listings
DBFILE:= curzon-showtimes.db
TARGET := $(TARGET_DIR)/$(SCRIPT)

.PHONY: install clean run
install: $(SCRIPT)
	# TODO update this
	sudo install -Dm755 $(SCRIPT) $(TARGET)

clean:
	rm -f $(DBFILE)

run:
	curzon-listings.sh
