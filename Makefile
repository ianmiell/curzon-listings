SCRIPT := curzon-listings.sh
TARGET_DIR := /opt/webhook
TARGET := $(TARGET_DIR)/$(SCRIPT)

.PHONY: install
install: $(SCRIPT)
	sudo install -Dm755 $(SCRIPT) $(TARGET)
