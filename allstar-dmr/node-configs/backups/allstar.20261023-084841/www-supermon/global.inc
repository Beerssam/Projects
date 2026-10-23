<?php
// Set the values to your parameters for
// Supermon 7.4+ variables - Paul Aidukas KN2R
// ONLY change text between quotes
//
// Your callsign Only:
$CALL = "KF0RIZ";
//
// Your name:
$NAME = "Samuel Beers";
//
// Your location:
$LOCATION = "Shawnee, Kansas";
//
// Second line header title:
$TITLE2 = "625730 Allstar Node";
//
// Third line header title:
$TITLE3 = "AllStarLink/EchoLink/Digital - Bridging Control Center";
//
// Background image - specify path if not /var/www/html/supermon
// Leaving BACKGROUND null "" results in BACKGROUND_COLOR:
$BACKGROUND = "background.jpg";
//
// Background color if no image:
$BACKGROUND_COLOR = "blue";
//
// Height of background - matches image height:
$BACKGROUND_HEIGHT = "124px";
//
//
// Enable [Database] button – For quick review of entire AllStar internal database:
$DATABASE_TXT = "/tmp/database.txt";
//
// Node number(s) to display, if Streaming Audio:
//$STREAMING_NODE = "1999";
//
// Node number(s) to display, if Archiving Audio:
//$ARCHIVING_NODE = "12345";
//
// Archive Web address, if Archiving Audio locally or remotely:
//$ARCHIVE_URL="/supermon/custom/archive/";
//
// Enable custom server name for Supermon browser tab:
$SMSERVERNAME = "12345 Cloud";
//
// Supermon screen REFRESH delay time in seconds
// Default is 21600 seconds, six hours:
$REFRESH_DELAY = "2700";
//
// Supermon program loop delay (polling) setting.
// Higher delay can significantly reduce your Supermon web server network bandwidth usage on large open systems.
// Default is 500000 (0.50 secs).
// Minimum setting is 300000 (0.30 seconds), maximum is 30000000, (30.0 seconds):
$SMLOOPDELAY = "700000";
//
// Show number of core dump files that may exist, IF any
//$SHOW_COREDUMPS = "yes";
//
// Show weather conditions and temperature for Zip code or Airport code, for your area:
$LOCALZIP = "66226";
//
// Set/show a Clickable personal or club logo tile-picture in Supermon header:
//$MY_TILE = "tile_name.jpg";
//$MY_TILE_URL = "http://anywhere.com";
//
// Set/show a second Clickable personal or club logo tile-picture2 in Supermon header:
//$MY_TILE2 = "usflag.jpg";
// $MY_TILE2 = "ukflag.jpg";
//$MY_TILE2_URL = "http://anywhere2.com";
//
// Enable the NEW Supermon button to launch any other Dashboard like DVSwitch or Pi-Star:
$DVM_URL_NAME = "Digital Dashboard";
$DVM_URL = "http://Pi-Star";
//$DVM_URL = "http://your_dvm_url.com";
//
// Enable a Maintainer email address link in your Supermon page footer:
//$MAINTAINER = "<a href=\"MailTo:WXYZ@whereever.com\">Name, WXYZ</a>";
//
// When your RPi or Cloud PC system is running on a LAN network with a router/firewall, you do NOT need this variable set!
// If your system is directly connected to the internet without a firewall/router,
// Supermon can hang trying to get both the WAN and LAN addresses.
// Set this variable to "yes" to disable checking for a LAN address and report only the WAN address.
// This will eliminate the hanging of Supermon in this case:
//$WANONLY = "yes";
//
?>


