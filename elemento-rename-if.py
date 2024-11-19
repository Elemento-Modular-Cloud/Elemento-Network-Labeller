#!/usr/bin/env python3

import time
import re
import json
import subprocess
from subprocess import Popen
from subprocess import PIPE

nm_connections = {}
new_ifaces = {}

def get_con_name(name):
    cmd = Popen(["nmcli","--terse", "con"], stdout=PIPE, stderr=PIPE, universal_newlines=True)
    out, err = cmd.communicate()
    cons = out.strip().split("\n")
    for con in cons:
        attrs = con.split(":")
        if attrs[3] != name:
            continue
        return attrs[0]
    return None

def get_iface_type(name):
    ip_cmd = Popen(["nmcli","--terse", "dev"], stdout=PIPE, stderr=PIPE, universal_newlines=True)
    out, err = ip_cmd.communicate()
    devs = out.strip().split("\n")
    for dev in devs:
        attrs = dev.split(":")
        if attrs[0] != name:
            continue
        return attrs[1]
    return None

def get_iface_speed(name):
    p = Popen(["ethtool", name], stdout=PIPE, stderr=PIPE, universal_newlines=True)
    out, err = p.communicate()
    slm = "Supported link modes:"
    slm_idx = out.find(slm) + len(slm)
    slm_dirty = out[slm_idx:].strip().split()
    slm_pattern = re.compile("^([0-9].*)/(Full)?(Half)?$")
    max_speed = 0
    for slm in slm_dirty:
        if slm_pattern.match(slm):
            speed = int(re.findall(r'\d+', slm)[0])
            max_speed = max(max_speed, speed)
    gbps_speed = str(max_speed / 1000)
    gbps_speed = gbps_speed[:gbps_speed.find(".")] if int(gbps_speed.split('.')[1]) == 0 else gbps_speed
    gbps_speed = gbps_speed + "Gb"
    return gbps_speed

def get_ifaces():
    # get ifaces with "ip" command
    ip_cmd = Popen(["ip","-details", "-json", "link"], stdout=PIPE, stderr=PIPE, universal_newlines=True)
    out, err = ip_cmd.communicate()
    ifaces = json.loads(out)
    return ifaces

def rename_iface(oldname, newname):
    global nm_connections 
    ip_commands = [["ip", "link", "set", "dev", oldname, "down"],
                   ["ip", "link", "set", "dev", oldname, "name", newname],
                   ["ip", "link", "set", "dev", newname, "up"]
                   ]
    nmcli_commands = [
                        ["nmcli", "dev", "set", nm_connections[oldname], "autoconnect", "yes"],
                        ["nmcli", "con", "modify", nm_connections[oldname], "connection.id", newname],
                        ["nmcli", "con", "modify", nm_connections[oldname], "connection.interface-name", newname],
                        ["nmcli", "con", "up",  nm_connections[oldname]]
                      ]

    for cmd in ip_commands:
        p = Popen(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        return_code = p.wait()
        if return_code != 0:
            out, err = p.communicate()
            print(cmd[0] + ":", err.strip())
        time.sleep(0.25)
        
    if oldname in nm_connections and nm_connections[oldname] is not None:
        for cmd in nmcli_commands:
            p = Popen(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
            return_code = p.wait()
            if return_code != 0:
                out, err = p.communicate()
                print(cmd[0] + ":", err.strip())
        time.sleep(0.25)
        
ifaces = get_ifaces()

for iface in ifaces:
    if iface["link_type"] not in ["ether"]:
        continue

    # get iface attributes
    ifname = iface.get("ifname")
    ifaddr = iface.get("permaddr") if iface.get("permaddr") is not None else iface.get("address")
    iftype = get_iface_type(ifname)
    gbps_speed = get_iface_speed(ifname)
    nm_connections[ifname] = get_con_name(ifname)

    link_type = "eth" + gbps_speed if iftype == "ethernet" else "wlan"
    # print("IFACE", link_type, ifaddr, "(" + ifname + ")")

    # construct a link-type hierarchical dictionary
    if link_type not in new_ifaces:
        new_ifaces[link_type] = []
    new_ifaces[link_type].append((ifaddr, ifname))

# dummy data for testing
# new_ifaces["eth2.5Gb"].append(('b4:2e:99:ab:39:a7', 'enp9s0'))
# new_ifaces["wlan"].append(('50:e0:85:f4:30:a4', 'wlp4s0'))

# generate new names for the interfaces
for link_type in new_ifaces.keys():
    new_ifaces[link_type].sort()
    for i, iface in enumerate(new_ifaces[link_type]):
        new_ifname = link_type + str(i)
        if iface[1] in ["lo", "docker0", "br0", "wg0"]:
            continue
        print("renaming " + iface[1] + " (" + iface[0] + ") to " + new_ifname)
        if iface[1]=="br0":
            print("Skipping br0")
            continue
        rename_iface(iface[1], new_ifname)


