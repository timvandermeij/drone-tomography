#!/bin/sh
cd /home/alarm/mobile-radio-tomography
stdbuf -oL -eL python2 mission_basic.py --vehicle-class Robot_Vehicle_Arduino_Full --geometry-class Geometry --servo-pins --distance-sensors --no-plot --no-viewer --speed 0.3 --rf-sensor-class XBee_CC2530_Sensor_Physical --synchronize --closeness 0 > logs/output$$.log 2> logs/error$$.log
