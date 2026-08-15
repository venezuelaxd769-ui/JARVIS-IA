#!/bin/sh
# this script runs when the app needs to poll input events from /dev/input/eventX.
# it polls input through a separate instance of veado, which it runs through pkexec
# in order to show a nice little window asking the user for root privilege.
# i'm not good with linux -- this is just the solution i came up with for hotkeys AHASHDFA
# doesn't need saying that you can just change this script as you wish

if [ "$(id -u)" != "0" ]; then
	pkexec "/bin/sh" "$(dirname "$1")/lib/input.sh" "$@"; RESULT=$?
	echo "#ended with $RESULT"
	if [ $RESULT -eq 126 ] || [ $RESULT -eq 127 ]; then
		echo "@denied"
		sleep 1
	fi
	exit 0
fi
echo "#running toolset from script"
cd "$(dirname "$1")"
"$1" --toolset LinuxInput
echo "#toolset ended!"
sleep 1
exit 0
