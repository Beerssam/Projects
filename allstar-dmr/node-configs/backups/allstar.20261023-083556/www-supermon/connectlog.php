<?php
include("session.inc");

// Author: Paul Aidukas KN2R (Copyright) July 15, 2013
// For ham radio use only, NOT for comercial use!
// Be sure to allow popups from your Allmon web server to your browser!!

?>
<html>
<head>
<title>Supermon Connection Log</title>
</head>
<body>
<pre>
<?php
	if ($_SESSION['sm61loggedin'] === true) {
		$file2 = "/var/log/asterisk/connectlog.2";
		$file1 = "/var/log/asterisk/connectlog.1";
		$file = "/var/log/asterisk/connectlog";

		echo "File: $file2\n-----------------------------------------------------------------\n";
		echo file_get_contents($file2);
		echo "\nFile: $file1\n-----------------------------------------------------------------\n";
		echo file_get_contents($file1);
		echo "\nFile: $file\n-----------------------------------------------------------------\n";
		echo file_get_contents($file);

	} else
		echo ("<br><h3>ERROR: You Must login to use this function!</h3>");
?>
</pre>
</body>
</html>
