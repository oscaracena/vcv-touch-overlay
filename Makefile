SHELL = /bin/bash

all:
	@echo "To install the script, run:"
	@echo "   make install-app DEST_DIR=XX RACK_SYSTEM_DIR=YY"

install-app: DEST_DIR        ?= /opt/vcv-to
install-app: RACK_SYSTEM_DIR ?= /opt/Rack2Free
install-app:
	sudo mkdir -p $(DEST_DIR)
	sudo cp -v utils/vcv-and-overlay.sh $(DEST_DIR)/
	sudo cp -v vcv-touch-overlay.py $(DEST_DIR)
	sudo desktop-file-install utils/vcv-and-overlay.desktop

	sudo sed -i "s|^RACK_SYSTEM_DIR=.*|RACK_SYSTEM_DIR=\"$(RACK_SYSTEM_DIR)\"|" \
		$(DEST_DIR)/vcv-and-overlay.sh
	sudo sed -i "s|^VTO_BIN=.*|VTO_BIN=\"$(DEST_DIR)/vcv-touch-overlay.py\"|" \
		$(DEST_DIR)/vcv-and-overlay.sh

	sudo sed -i "s|^Exec=.*|Exec=$(DEST_DIR)/vcv-and-overlay.sh|" \
		/usr/share/applications/vcv-and-overlay.desktop
	sudo sed -i "s|^Icon=.*|Icon=$(RACK_SYSTEM_DIR)/res/icon.png|" \
		/usr/share/applications/vcv-and-overlay.desktop
