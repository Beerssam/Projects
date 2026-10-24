<?php include("session.inc"); ?>
<?php include "header.inc"; ?>
<p> To Login you must Activate a Node number first from the Menu Bar, then Login using the Header Login link.
<br><br>
 Welcome to <b><i><?php echo $CALL; ?></i></b> and associated AllStar nodes.
<br><br>
This Supermon web site is for monitoring and managing ham radio
<a href="http://allstarlink.org" target="_blank">AllStar</a> and app_rpt
node linking and <a href="http://micro-node.com/thin-m1.html" target="_blank">RTCM clients</a>.
This is version 7.4+ of Supermon which includes a vast number of internal and UI improvements over Allmon version 2.1.
</p>
<p>
On the menu bar click on the node numbers to see, and manage if you have a login ID, each local node.
These pages dynamically display any remote nodes that are connected to it.
When a signal is received the remote node will move to the top of the list and will have a dark-blue background.
The most recently received nodes will always be at the top of the list.
<ul>
<li>
The <b>Direction</b> column shows <b>IN</b> when another node connected to us and <b>OUT</b> if the connection was made from us.
</li>
<li>
The <b>Mode</b> column will show <b>Transceive</b> when this node will transmit and receive to/from the connected node. It will show <b>Receive Only</b> or <b>Local Monitor</b> if this node only receives from the connected node.
</li>
</ul>
</p>
<p>
Any Voter pages will show RTCM receiver details. The bars will move in near-real-time as the signal strength varies.
The voted receiver will turn green indicating that it is being repeated.
The numbers are the relative signal strength indicator, RSSI. The value ranges from 0 to 255, a range of approximately 30db.
A value of zero means that no signal is being selected.
The color of the bars indicate the type of RTCM client as shown on the key below the voter display.
</p>
<br>

<div class="classictemplate template" style="display: block;">
<style type="text/css">
  #groupsio_embed_signup input {border:1px solid #999; -webkit-appearance:none;}
  #groupsio_embed_signup label {display:block; font-size:16px; padding-bottom:10px; font-weight:bold;}
  #groupsio_embed_signup .email {display:block; padding:8px 0; margin:0 4% 10px 0; text-indent:5px; width:58%; min-width:130px;}
  #groupsio_embed_signup {
    background:#fff; clear:left; font:14px Helvetica,Arial,sans-serif;
  }
  #groupsio_embed_signup .button {

      width:25%; margin:0 0 10px 0; min-width:90px;
      background-image: linear-gradient(to bottom,#337ab7 0,#265a88 100%);
      background-repeat: repeat-x;
      border-color: #245580;
      text-shadow: 0 -1px 0 rgba(0,0,0,.2);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.15),0 1px 1px rgba(0,0,0,.075);
      padding: 5px 10px;
      font-size: 12px;
      line-height: 1.5;
      border-radius: 3px;
      color: #fff;
      background-color: #337ab7;
      display: inline-block;
      margin-bottom: 0;
      font-weight: 400;
      text-align: center;
      white-space: nowrap;
      vertical-align: middle;
    }
</style>

<div id="groupsio_embed_signup">
<form action="https://groups.io/g/Supermon/signup?u=381513226132993244" method="post" id="groupsio-embedded-subscribe-form" name="groupsio-embedded-subscribe-form" target="_blank">
    <div id="groupsio_embed_signup_scroll">
      <label for="email" id="templateformtitle">Subscribe to the Official/Original Supermon Support Group (Supermon@groups.io)</label>
      <input type="email" value="" name="email" class="email" id="email" placeholder="email address" required="">

    <div style="position: absolute; left: -5000px;" aria-hidden="true"><input type="text" name="b_381513226132993244" tabindex="-1" value=""></div>
    <div id="templatearchives"></div>
    <input type="submit" value="Subscribe" name="subscribe" id="groupsio-embedded-subscribe" class="button">
  </div>
</form>
</div>
</div>
<br>

<?php include "footer.inc"; ?>
