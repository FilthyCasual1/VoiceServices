#!/bin/sh
# Console appliance setup. A menu entry only changes settings after confirmation.
set -eu
[ "$(id -u)" = 0 ] && [ -f /etc/openwrt_release ] || { echo 'Run insap-setup as root on OpenWrt.' >&2; exit 1; }
command -v whiptail >/dev/null || { echo 'Install the optional whiptail package for console setup, or use the browser wizard.' >&2; exit 1; }
export PYTHONPATH=/opt/serviceready/app
while true; do
 choice=$(whiptail --output-fd 1 --title 'INSAP appliance configuration' --menu 'Choose a setup area. Apply each change explicitly.' 18 72 8 \
  browser 'Browser setup address and ownership code' \
  network 'DHCP or static IPv4 for the management interface' \
  ntp 'Network time servers' \
  tools 'Hypervisor guest tools status' \
  exit 'Save and exit') || exit 0
 case "$choice" in
  browser)
   summary=$(python3 /opt/serviceready/openwrt-menu.py status)
   whiptail --title 'Browser setup' --msgbox "$summary" 15 76 ;;
  network)
   interface=$(whiptail --output-fd 1 --inputbox 'OpenWrt logical interface (normally lan)' 8 60 lan) || continue
   method=$(whiptail --output-fd 1 --menu 'Address method' 10 60 2 dhcp 'Follow the network DHCP lease' static 'Set a fixed IPv4 address') || continue
   address='';gateway='';dns=''
   if [ "$method" = static ]; then
    address=$(whiptail --output-fd 1 --inputbox 'IPv4 address/prefix, for example 192.168.1.20/24' 8 70) || continue
    gateway=$(whiptail --output-fd 1 --inputbox 'IPv4 gateway' 8 60) || continue
    dns=$(whiptail --output-fd 1 --inputbox 'DNS addresses, separated by spaces' 8 60) || continue
   fi
   whiptail --yesno 'Apply the management network change? Your browser connection may move to another address. Keep this VM console open for recovery.' 10 72 || continue
   if output=$(python3 /opt/serviceready/openwrt-menu.py network "$interface" "$method" "$address" "$gateway" "$dns" 2>&1); then
    whiptail --msgbox "$output" 10 72
   else whiptail --title 'Settings retained / restore required' --msgbox "$output" 15 76; fi ;;
  ntp)
   servers=$(whiptail --output-fd 1 --inputbox 'NTP server names or addresses, separated by spaces' 8 72 '0.openwrt.pool.ntp.org 1.openwrt.pool.ntp.org') || continue
   whiptail --yesno 'Save these NTP servers and restart time synchronization?' 8 72 || continue
   output=$(python3 /opt/serviceready/openwrt-menu.py ntp "$servers" 2>&1) || true
   whiptail --msgbox "$output" 12 76 ;;
  tools)
   output=$(python3 /opt/serviceready/openwrt-menu.py tools)
   whiptail --msgbox "$output" 14 76 ;;
  exit) clear; exit 0 ;;
 esac
done
