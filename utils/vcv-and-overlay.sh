#!/bin/bash

# NOTE: define your VCV Rack 2 / touch overlay paths here
# -------------------------------------------------------
RACK_SYSTEM_DIR="/opt/Rack2Free"
VTO_BIN=/opt/vcv-to/vcv-touch-overlay.py
# -------------------------------------------------------

# launch vcv rack
cd ${RACK_SYSTEM_DIR}
./Rack &
PID_RACK=$!

# launch touch overlay
sleep 1
${VTO_BIN} &
PID_VTO=$!

wait $PID_RACK

# stop touch overlay
kill $PID_VTO 2>/dev/null
wait $PID_VTO 2>/dev/null
