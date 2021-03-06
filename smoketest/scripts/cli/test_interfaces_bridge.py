#!/usr/bin/env python3
#
# Copyright (C) 2020 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import unittest

from base_interfaces_test import BasicInterfaceTest
from glob import glob
from netifaces import interfaces
from vyos.ifconfig import Section
from vyos.util import cmd
import json

class BridgeInterfaceTest(BasicInterfaceTest.BaseTest):
    def setUp(self):
        super().setUp()

        self._test_ipv6 = True
        self._test_vlan = True
        self._test_qinq = True
        self._test_mirror = True

        self._base_path = ['interfaces', 'bridge']
        self._interfaces = ['br0']

        self._members = []
        # we need to filter out VLAN interfaces identified by a dot (.)
        # in their name - just in case!
        if 'TEST_ETH' in os.environ:
            self._members = os.environ['TEST_ETH'].split()
        else:
            for tmp in Section.interfaces("ethernet"):
                if not '.' in tmp:
                    self._members.append(tmp)
            
            self.session.set(['interfaces','dummy','dum0'])
            self.session.set(['interfaces','dummy','dum1'])
            self.session.set(['interfaces','bonding','bond1','member','interface','dum0'])
            self.session.set(['interfaces','bonding','bond1','member','interface','dum1'])
            self._members.append('bond1')

        self._options['br0'] = []
        for member in self._members:
            self._options['br0'].append(f'member interface {member}')
    
    def tearDown(self):
        self.session.delete(['interfaces','bonding'])
        self.session.delete(['interfaces','dummy'])
        super().tearDown()

    def test_add_remove_member(self):
        """ Add member interfaces to bridge and set STP cost/priority """
        for interface in self._interfaces:
            base = self._base_path + [interface]
            self.session.set(base + ['stp'])
            self.session.set(base + ['address', '192.0.2.1/24'])

            cost = 1000
            priority = 10
            # assign members to bridge interface
            for member in self._members:
                base_member = base + ['member', 'interface', member]
                self.session.set(base_member + ['cost', str(cost)])
                self.session.set(base_member + ['priority', str(priority)])
                cost += 1
                priority += 1

        # commit config
        self.session.commit()

        # check member interfaces are added on the bridge
        bridge_members = []
        for tmp in glob(f'/sys/class/net/{interface}/lower_*'):
            bridge_members.append(os.path.basename(tmp).replace('lower_', ''))

        for member in self._members:
            self.assertIn(member, bridge_members)

        # delete all members
        for interface in self._interfaces:
            self.session.delete(self._base_path + [interface, 'member'])

        self.session.commit()
    
    def test_vlan_filter(self):
        """ Add member interface to bridge and set VLAN filter """
        for interface in self._interfaces:
            base = self._base_path + [interface]
            self.session.set(base + ['vif', '1','address', '192.0.2.1/24'])
            self.session.set(base + ['vif', '2','address','192.0.3.1/24'])

            vlan_id = 101
            allowed_vlan = 2
            allowed_vlan_range = '4-9'
            # assign members to bridge interface
            for member in self._members:
                base_member = base + ['member', 'interface', member]
                self.session.set(base_member + ['allowed-vlan', str(allowed_vlan)])
                self.session.set(base_member + ['allowed-vlan', allowed_vlan_range])
                self.session.set(base_member + ['native-vlan', str(vlan_id)])
                vlan_id += 1

        # commit config
        self.session.commit()
        
        # Detect the vlan filter function
        for interface in self._interfaces:
            with open(f'/sys/class/net/{interface}/bridge/vlan_filtering', 'r') as f:
                flags = f.read()
                self.assertEqual(int(flags), 1)
        
        # Execute the program to obtain status information
        
        json_data = cmd('bridge -j vlan show', shell=True)
        
        vlan_filter_status = None
        
        vlan_filter_status = json.loads(json_data)
            
        
        if vlan_filter_status is not None:
            for interface_status in vlan_filter_status:
                ifname = interface_status['ifname']
                for interface in self._members:
                    vlan_success = 0;
                    if interface == ifname:
                        vlans_status = interface_status['vlans']
                        for vlan_status in vlans_status:
                            vlan_id = vlan_status['vlan']
                            flag_num = 0
                            if 'flags' in vlan_status:
                                flags = vlan_status['flags']
                                for flag in flags:
                                    flag_num = flag_num +1
                            if vlan_id == 2:
                                if flag_num == 0:
                                    vlan_success = vlan_success + 1
                            else:
                                for id in range(4,10):
                                    if vlan_id == id:
                                        if flag_num == 0:
                                            vlan_success = vlan_success + 1
                                if vlan_id >= 101:
                                    if flag_num == 2:
                                        vlan_success = vlan_success + 1
                        if vlan_success >= 7:
                            self.assertTrue(True)
                        else:
                            self.assertTrue(False)
                        
        else:
            self.assertTrue(False)
        
            
        

        # check member interfaces are added on the bridge
        
        for interface in self._interfaces:
            bridge_members = []
            for tmp in glob(f'/sys/class/net/{interface}/lower_*'):
                bridge_members.append(os.path.basename(tmp).replace('lower_', ''))

            for member in self._members:
                self.assertIn(member, bridge_members)

        # delete all members
        for interface in self._interfaces:
            self.session.delete(self._base_path + [interface, 'member'])

        self.session.commit()

    def test_vlan_members(self):
        """ T2945: ensure that VIFs are not dropped from bridge """

        self.session.set(['interfaces', 'ethernet', 'eth0', 'vif', '300'])
        self.session.set(['interfaces', 'bridge', 'br0', 'member', 'interface', 'eth0.300'])
        self.session.commit()

        # member interface must be assigned to the bridge
        self.assertTrue(os.path.exists('/sys/class/net/br0/lower_eth0.300'))

        # add second bridge member
        self.session.set(['interfaces', 'ethernet', 'eth0', 'vif', '400'])
        self.session.commit()

        # member interface must still be assigned to the bridge
        self.assertTrue(os.path.exists('/sys/class/net/br0/lower_eth0.300'))

        # remove VLAN interfaces
        self.session.delete(['interfaces', 'ethernet', 'eth0', 'vif', '300'])
        self.session.delete(['interfaces', 'ethernet', 'eth0', 'vif', '400'])
        self.session.commit()


if __name__ == '__main__':
    unittest.main()

