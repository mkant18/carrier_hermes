$wslIp = (wsl -- hostname -I 2>$null).Trim().Split(" ")[0]
if ($wslIp) {
  netsh interface portproxy delete v4tov4 listenaddress=127.0.0.1 listenport=11434 2>$null
  netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=11434 connectaddress=$wslIp connectport=11434
}
