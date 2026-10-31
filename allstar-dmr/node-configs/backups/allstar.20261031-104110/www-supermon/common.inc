<?php
//
//	System specific parameters...
//	NOTE: DO NOT MODIFY!
//	THIS FILE WILL BE OVERWRITTEN BY PACKAGE UPDATES!
//
// Title in header when logged in
$TITLE_LOGGED = "Supermon 7.4+ (ASL) AllStar Manager";
//
// Title in header when not logged in
$TITLE_NOT_LOGGED = "Supermon 7.4+ (ASL) AllStar Monitor";
//
// Webserver access log
$WEB_ACCESS_LOG = "/var/log/apache2/access.log";
//
// Webserver error log
$WEB_ERROR_LOG = "/var/log/apache2/error.log";
//
// Asterisk message log
$ASTERISK_LOG = "/var/log/asterisk/messages";
//
// AllStar allmon database
$ASTDB_TXT = "/var/www/html/supermon/astdb.txt";
//
// AllStar rpt_extnodes file --- not present in DNS mode.
$EXTNODES = "/var/lib/asterisk/rpt_extnodes";
//
// AllStar Echolink database dump
$ECHO_DB = "/tmp/echolink.db.gz";
//
// Private AllStar nodelist
$PRIVATENODES = "/var/www/html/supermon/privatenodes.txt";
//
//	IRLP related...
$IRLP_CALLS = "/tmp/irlpdata.txt.gz";
$IRLP_LOG = "/home/irlp/log/messages";
//
// Cache version number info.
$file = `find /tmp/asterisk_version /run/asterisk.pid /etc/allstar_version -printf "%T@  %p\n" 2>/dev/null | sort -nr | /usr/bin/awk '{if (NR == 1) printf ("%s", $2)}'`;
if ($file == "/tmp/asterisk_version")
        $version= `cat /tmp/asterisk_version`;
else
        $version = `export TERM=vt100; sudo asterisk -rx "core show version" |/usr/bin/awk '{print $2}' | tee /tmp/asterisk_version`;

$version="Asterisk $version";
//echo "<p>$file, $version</p>";
//
// Make sure this is not hamvoip "Vx.xrc" code
$pattern="/ [0-9].[0-9]rc[0-9]/";
if (preg_match($pattern, $version, $match)) {
	$system_type = "allstarlink";
} else {
	// Add other types if needed here
	// $system_type="";
	$system_type = "allstarlink";
}
//
//	Paths to various programs called from php...
$ASTERISK =	"/usr/sbin/asterisk";
$AWK =		"/usr/bin/awk";
$CAT =		"/bin/cat";
$CUT =		"/usr/bin/cut";
$DATE =		"/bin/date";
$DNSQUERY =     "/usr/local/sbin/supermon/dns-query";
$EGREP =	"/bin/egrep";
$GREP =		"/bin/grep";
$HEAD =		"/usr/bin/head";
$HOSTNAME =	"/bin/hostname";
$IFCONFIG =	"/sbin/ifconfig";
$JOURNALCTL =	"/bin/journalctl";
$MBUFFER =	"/usr/local/bin/mbuffer";
$SED =		"/bin/sed";
$SUDO =		"export TERM=vt100 && /usr/bin/sudo";
$TAIL =		"/usr/bin/tail";
$UPTIME =	"/usr/bin/uptime";
$WGET =		"/usr/bin/wget";
$ZCAT =		"/bin/zcat";

if (file_exists($IRLP_LOG))
	$IRLPLOG = true;
else
	$IRLPLOG = false;

if (file_exists($IRLP_CALLS))
	$IRLP = true;
else
	$IRLP = false;

if (file_exists($EXTNODES))
	$EXTN = true;
else
	$EXTN = false;
?>
