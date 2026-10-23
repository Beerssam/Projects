<?php
include('amifunctions.inc');
include('session.inc');

if ($_SESSION['sm61loggedin'] !== true) {
        die("Please login to use Control Panel functions.\n");
}

// Refactored: Paul Aidukas KN2R (Copyright) July 15, 2013
// For ham radio use only, NOT for comercial use!

#print_r($_GET);
$node = @trim(strip_tags($_GET['node']));
$cmd = @trim(strip_tags($_GET['cmd']));

// Read supermon INI file
if (!file_exists('allmon.ini')) {
    die("Couldn't load allmon ini file.\n");
}
$config = parse_ini_file('allmon.ini', true);

// Check if node exists in ini
if (!isset($config[$node])) {
    die("Node $node is not in allmon ini file.");
}

// Set up connection
$fp = AMIconnect($config[$node]['host']);
if (FALSE === $fp) {
    die("Could not connect to host.");
}

// Login 
if (FALSE === AMIlogin($fp, $config[$node]['__REDACTED__'], $config[$node]['__REDACTED__'])) {
    die("Could not login.");
}

// Substitute node number
$cmdString = preg_replace("/%node%/", $node, $cmd);

// AMI needs an ActionID so we can find our own response
$actionRand = mt_rand(); 
$actionID = 'cpAction_' . $actionRand;

if ((@fwrite($fp,"ACTION: COMMAND\r\nCOMMAND: $cmdString\r\nActionID: $actionID\r\n\r\n")) > 0 ) {
    $rptStatus = AMIget_response($fp, $actionID);
    print "<pre>\n===== $cmdString =====\n";
    print $rptStatus;
    #print "===== end =====\n</pre>\n";
} else {
    die("Get node $cmdString failed!");
}
?>

