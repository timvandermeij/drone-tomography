[![Build status](https://travis-ci.org/timvandermeij/mobile-radio-tomography.svg)](https://travis-ci.org/timvandermeij/mobile-radio-tomography)

The mobile radio tomography framework provides tools for performing mobile radio
tomographic imaging using XBee chips mounted on unmanned vehicles such as rover 
cars or drones. This framework is the result of research projects and master 
theses by Tim van der Meij ([@timvandermeij](https://github.com/timvandermeij)) 
and Leon Helwerda ([@lhelwerd](https://github.com/lhelwerd)). The research is 
performed in collaboration with Leiden University and CWI Amsterdam, both 
located in the Netherlands.

Prerequisites
=============

In order to use the framework, you must have the following software installed 
on your system. The framework has been developed for Linux, but can be made to 
work on Windows or any other operating system since all prerequisites are also 
available for those systems, perhaps with slightly different installation 
procedures.

* Git
* Binaries and development headers for the [LIRC](http://www.lirc.org/) package 
  for remote control support. Check whether and how your package manager 
  provides these packages, otherwise you can retrieve them from the LIRC 
  website itself.
* Python 2.7. Note that Python 3 cannot be used at this moment.
* PyQt4
* `pip` for Python 2.7. `pip` is often not available on extremely old and bare
  systems. If it is not delivered by a package manager, one can also
  [install it with get-pip.py](https://pip.pypa.io/en/latest/installing.html).
  Ensure that you have the correct version of `pip` with `pip2 --version`. See 
  the [Python packages](#python-packages) section below for installing the 
  required packages using `pip`.
* ArduPilot for vehicle simulation. See the [ArduPilot](#ardupilot) section 
  below for more details.

For all commands in this file, replace `python2` with `python`, and `pip2` with 
`pip` if your operating system does not need to distinguish between Python 
2 and Python 3.

Python packages
---------------
Use `pip2 install --user <package>` to install or upgrade each of the following 
packages, or `pip2 install -r requirements.txt` to install all of them in one 
go. The packages are sorted by purpose as follows:

* General packages:
    * matplotlib
    * NumPy
    * scipy
* Control panel:
    * PyQtGraph
    * markdown
    * py-gfm
* Physical sensor/communication interfaces:
    * pyserial
    * RPi.GPIO
    * wiringpi
    * xbee
    * pylirc2
    * pyudev
* Vehicle trajectory mission interfaces:
    * lxml
    * pexpect
    * pymavlink
    * mavproxy
    * dronekit
* Environment simulation:
    * PyOpenGL
    * simpleparse
    * PyVRML97 (you may need to use `pip2 install --user "PyVRML97==2.3.0b1"`)
    * PyDispatcher
    * pyglet
* Testing:
    * mock
    * coverage
    * pylint

ArduPilot
---------

Download the latest code using:

    $ git clone https://github.com/diydrones/ardupilot.git

Then, add the following line to your `~/.bashrc`:

    export PATH=$PATH:$HOME/ardupilot/Tools/autotest

In order to use the map display of ArduPilot, make sure that OpenCV and 
wxWidgets as well as their respective Python bindings are installed and 
available. If not, the following directions might help you get it:

* OpenCV: This is sometimes provided by the package manager. It can also be 
  installed from the [official download](http://opencv.org/downloads.html) 
  using the appropriate 
  [documentation](http://docs.opencv.org/2.4/doc/tutorials/introduction/table_of_content_introduction/table_of_content_introduction.html). 
  Note that for Linux, you must change the install prefix for `cmake` if you do 
  not have superuser rights. You can speed up the installation by passing `-j4` 
  to the `cmake` command.
* wxWidgets: Again, if this is not provided by the package manager, see an 
  [explanation](http://wiki.wxpython.org/How%20to%20install%20wxPython) on how 
  to install from source. This requires wxGTK as well as the wxWidgets library 
  itself: these are combined within 
  a [download](http://www.wxwidgets.org/downloads/). You can install without 
  superuser rights using `./configure --with-gtk --prefix=$HOME/.local`.

Cloning the repository
======================

The first step is to clone the repository to obtain a local copy of the 
code. Open a terminal and run the following commands.

    $ git clone https://github.com/timvandermeij/mobile-radio-tomography.git
    $ cd mobile-radio-tomography

Running the tools
=================

Now that we have a copy of the software, we can run the tools. Use `sudo` in 
front of commands if your user is not part of the `dialout` or `uucp` group.

XBee configurator
-----------------

The XBee configurator is used to quickly prepare all XBee sensors in the
network. Launch the configurator with `python2 xbee_configurator.py` to
get started. You might need to adjust the settings for the `xbee_configurator`
component in `settings.json`, for example to set the right port if the
default port is not correct (or use the command line options). After starting
the tool, the instructions for configuring each sensor are displayed on the
screen. The tool takes care of setting all required parameters.

Vehicle mission
---------------

The trajectory mission sets up an unmanned aerial vehicle (UAV) and directs it
to move and rotate within its environment. The script supports various mission
types and simulation modes. You can run it using the ArduPilot simulator with
the following commands:

    $ sim_vehicle.sh -v ArduCopter --map

One can also use different vehicle types, such as APMrover2 for a ground rover.
Then start the mission script using the following command in another terminal:

    $ python2 mission_basic.py --vehicle Dronekit_Vehicle

This starts the mission with default settings from `settings.json`. The
ArduPilot simulator provides an overhead map showing the copter's position.
The mission monitor has a map in memory that shows objects in the environment
during simulation as well as detected points from a distance sensor. It also
provides a 3D viewer of the simulated objects.

You can also start the mission monitor without ArduPilot simulation using
`python2 mission_basic.py`. In this case, the vehicle is simulated on our own,
and no overhead map is provided other than the memory map. The command allows
changing settings from their defaults using arguments. You can provide a VRML
scene file to retrieve simulated objects from using the `--scenefile` option,
change the geometry from a spherical coordinate system (`Geometry_Spherical`)
to a flat meter-based coordinate system using `--geometry-class Geometry`, or
set sensor positioning angles, for example `--sensors 0 90 -90`. Many other 
options are available for simulating various missions and sensor setups, and
the command `python2 mission_basic.py --help` provides a list of them. The most
important setting might be the mission class to use for calculating what
trajectory to take. You can choose one of the classes in `trajectory/Mission.py`
using `--mission-class <Mission_Name>`.

XBee sensor (simulator)
-----------------------

The XBee sensor simulator is used to simulate the behavior of an XBee
sensor network. This is especially useful for determining communication
schemes for the sensors. Start the tool on a laptop or desktop computer
with `python2 xbee_sensor_simulator.py` in a terminal to get output in the
terminal. Settings for the simulation, such as the number of sensors in the
network, can be altered in the `settings.json` file.

XBee sensor (physical)
----------------------

The physical XBee sensor code controls one XBee chip connected to the
device via USB. Such a device can either be a computer or a Raspberry
Pi. Start `screen` and run `python2 xbee_sensor_physical.py` to
activate the XBee chip mounted onto an XBee USB dongle. Each sensor
constantly receives packets (asynchronously), but sends packets according
to a fixed TDMA schedule as defined by the settings in `settings.json`.

To create the setup, first plug the ground station XBee chip into a USB
port of the ground station computer. Start the physical XBee sensor code
as mentioned above and observe that nothing is happening yet. Then, for
each other XBee chip in the network, power up the accompanying Raspberry
Pi, connect it to the ground station computer via an Ethernet cable as 
described in the Raspberry Pi document, plug in the XBee USB dongle
and start the physical XBee sensor code as mentioned above. You should now
see packets arriving in the ground station's terminal. Note that once the
process is running, you can detach the screen and disconnect the Ethernet
cable to have unconnected nodes that you can move around (assuming that
they are powered by a battery pack).

Distance sensor (physical)
--------------------------

We assume that you have setup a Raspberry Pi with Arch Linux ARM and
that you have connected the HC-SR04 sensor. This tool must run on the
Raspberry Pi. Start the tool with `python2 distance_sensor_physical.py`
to receive continuous measurements from the distance sensor. Change the pin
numbers for the trigger and echo pins in `settings.json` if you have used
different pin numbers when connecting the HC-SR04 sensor to the Raspberry Pi.

Infrared sensor
---------------

We assume that you have setup a Raspberry Pi with Arch Linux ARM and
that you have connected the TSOP38238 sensor. Make sure that LIRC is setup
correctly on the device (refer to the `docs` folder for more information on
this). This tool must be run on the Raspberry Pi. Start the tool with
`python2 infrared_sensor.py` and use a Sony RM-SRB5 remote. Press the play
and stop buttons on the remote and verify that the callback functions are
triggered.

You can change the remote that you wish to use. To do so, create or download
the `lircd.conf` file and place it in the `control/remotes` folder. Then
create a `lircrc` file using the same remote name there to bind the buttons
to the events. Finally change the remote name in the settings file.

Planner
-------

You can use the planning problem to generate random sensor positions and 
optimize them according to certain objectives, such as intersections at each 
grid pixel in the sensor network, sensor distances and vehicle move distances. 
You can start the planner in a terminal with `python2 plan_reconstruct.py`, or 
use the planning view. See [its control panel section](#planning-view) for more 
details. The terminal-based planner supports exporting the resulting positions 
in JSON format.

Control panel
-------------

The control panel is a graphical user interface that can be run on the ground 
station to provide status information and interfaces to tools. Run `make`, 
`make control_panel` or `python2 control_panel.py` in a terminal to open the 
control panel.

The control panel consists of various views that provide different details and 
tools, but work in concert with each other. We list the various views below.

### Loading view

When starting the control panel, it starts in a splash screen that is 
responsible for setting up XBee-related components.

The loading view checks whether a physical XBee sensor configured as a ground 
station sensor is connected through USB; otherwise, it waits for its insertion. 
If you do not have a physical XBee, then use the button to switch to the 
simulated version or run `python2 control_panel.py 
--controller-xbee-simulation` to start the control panel in this mode.

### Devices view

The devices view displays status information about the XBee sensors in the 
network. It displays their numerical identifier, their category type, their 
address identifier and their joined status. The number of sensors is determined 
by a setting; adjust this setting in the [settings view](#settings-view) if 
necessary. If not all sensors are detected, ensure that the vehicles are 
completely started and use the Refresh button to discover them.

### Planning view

The planning view is an interface to the planning problem algorithm runner. It 
makes it possible generate random sensor positions and optimize them. The 
positions around the sensor network may be at continuous or grid-based discrete 
locations. The multiobjective optimization algorithm attempts to find feasible 
positioning solutions for which no other known solution is better in all 
objectives. You can tune the algorithm and problem parameters using the 
settings toolboxes.

It is possible to see the progress of the Pareto front, statistics and 
individual solutions during the run, so that you can see whether the run is 
going to be useful. Afterward, you can select a solution, whose sensor 
positions are sorted and assigned over the vehicles in such a way to decrease 
the total time needed for the mission.

### Reconstruction view

The reconstruction view converts a dataset, dump or XBee data stream with 
signal strength measurements to input for the reconstructor, such as weight 
matrices and grid pixel data. The result of the reconstruction is visualized as 
a set of two-dimensional images. We provide multiple reconstructors:

* SVD
* Total variation
* Truncated SVD

The settings panels allow you to change the reconstructor and start the 
reconstruction and visualization process. The raw data is shown in a graph and 
table form. The stream source can also be recorded to a JSON dump format for 
calibration or analysis.

### Waypoints view

The waypoints view makes it possible to define a mission when the vehicles are 
operating in the `Mission_XBee` mission. You can add waypoints in each table 
and optionally synchronize between vehicles at each waypoint. It is possible to 
import and export JSON waypoints for later usage. The waypoints are sent to the 
vehicles using custom packets.

### Settings view

The settings view is a human-friendly interface to the settings files. You can 
change all settings in this interface, sorted by component and with 
descriptions and a search filter. Validation checks ensure that the settings 
values are correct. The settings can be saved in override files on the ground 
station and also sent to the vehicles, selectable in the save dialog. If some 
vehicles are not selectable, return to the [devices view](#devices-view) to 
discover them.

Running the tests
=================

The framework contains tests to ensure that all components behave the way
we expect them to behave and therefore to reduce the risk of introducing
regressions during development. The tests also include code coverage reports 
and other options for profiling and benchmarking. The tests have to be executed 
from the root folder using the following command:

    $ make test

This command is executed automatically by Travis CI for each pull request
or push to a branch.

Code style
----------

Compatibility with the `pylint` code style checker is provided to allow testing 
whether the code follows a certain coding standard and contains no other 
errors. Some reports may be disabled in `.pylintrc` or through plugins. You can 
use `pylint mobile-radio-tomography` to scan all files, which is quite slow.

During development, you can enable lint checks in your editor to receive code 
style help for the currently edited file on the go. For Vim, you can enable 
[Syntastic](https://github.com/scrooloose/syntastic) or use an older [pylint 
compiler script](http://www.vim.org/scripts/script.php?script_id=891). See the 
[pylint integration documentation](https://docs.pylint.org/ide-integration) for 
other editors.

License
=======

The framework is licensed under a GPL v3 license. Refer to the `LICENSE`
file for more information.
