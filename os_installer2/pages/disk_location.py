#!/bin/true
# -*- coding: utf-8 -*-
#
#  This file is part of os-installer
#
#  Copyright 2013-2016 Ikey Doherty <ikey@solus-project.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 2 of the License, or
#  (at your option) any later version.
#

from .basepage import BasePage
import parted


class InstallerDiskLocationPage(BasePage):
    """ Disk location selection. """

    had_init = False

    def __init__(self):
        BasePage.__init__(self)

    def get_title(self):
        return "Where should we install?"

    def get_name(self):
        return "disk-location"

    def get_icon_name(self):
        return "drive-harddisk-system-symbolic"

    def init_view(self):
        """ Prepare for viewing... """
        if self.had_init:
            return
        self.had_init = True

        # Scan parts
        dm = self.info.owner.get_disk_manager()
        perms = self.info.owner.get_perms_manager()
        dm.scan_parts()

        perms.up_permissions()
        for item in dm.devices:
            disk = None
            try:
                p = parted.getDevice(item)
                disk = parted.Disk(p)
            except Exception as e:
                print("Cannot probe disk: {}".format(e))
                continue
            if not disk:
                continue
            print("Got disk of type: {}".format(disk.type))
            sz = dm.get_disk_size_string(disk)
            print("Disk: {} {}".format(dm.get_disk_model(item), sz))
        print("Debug: {}".format(" ".join(dm.devices)))
        perms.down_permissions()

    def prepare(self, info):
        self.info = info
        self.init_view()