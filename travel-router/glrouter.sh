#!/usr/bin/env sh
# Deploy the beerswifi cert to the GL-MT3000 (root@10.167.65.134, ZeroTier).
# Router has no sftp-server (scp fails) -> pipe the files over ssh.
# GL nginx ignores the init-script reload -> HUP the master directly.
glrouter_deploy() {
  _ckey="$2"
  _cfullchain="$5"
  _target="root@10.167.65.134"
  _info "Deploying cert to GL-MT3000"
  ssh -o BatchMode=yes "$_target" 'cat > /etc/nginx/nginx.cer' < "$_cfullchain" || return 1
  ssh -o BatchMode=yes "$_target" 'cat > /etc/nginx/nginx.key' < "$_ckey" || return 1
  ssh -o BatchMode=yes "$_target" 'kill -HUP $(ps w | grep "[m]aster process" | awk "{print \$1}")' || return 1
  return 0
}
