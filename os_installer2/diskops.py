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

from os_installer2 import format_size_local
import parted
import subprocess


class BaseDiskOp:
    """ Basis of all disk operations """

    device = None
    errors = None
    part_offset = 0
    disk = None

    def __init__(self, device):
        self.device = device

    def describe(self):
        """ Describe this operation """
        return None

    def apply(self, disk, simulate):
        """ Apply this operation on the given (optional) disk"""
        print("IMPLEMENT ME!")
        return False

    def get_errors(self):
        """ Get the errors, if any, encountered """
        return self.errors

    def set_errors(self, er):
        """ Set the errors encountered """
        self.errors = er

    def set_part_offset(self, newoffset):
        """ Useful only for new partitions """
        self.part_offset = newoffset


class DiskOpCreateDisk(BaseDiskOp):
    """ Create a new parted.Disk """

    disk = None
    label = None

    def __init__(self, device, label):
        BaseDiskOp.__init__(self, device)
        self.label = label

    def describe(self):
        return "Create {} partition table on {}".format(
            self.label, self.device.path)

    def apply(self, unused_disk, simulate):
        """ Construct a new labeled disk """
        try:
            d = parted.freshDisk(self.device, self.label)
            self.disk = d
        except Exception as e:
            self.set_errors(e)
            return False
        return True


class DiskOpCreatePartition(BaseDiskOp):
    """ Create a new partition on the disk """

    fstype = None
    size = None
    ptype = None
    part = None
    part_end = None

    def __init__(self, device, ptype, fstype, size):
        BaseDiskOp.__init__(self, device)
        self.ptype = ptype
        self.fstype = fstype
        self.size = size
        if not self.ptype:
            self.ptype = parted.PARTITION_NORMAL

    def get_all_remaining_geom(self, disk, device, start):
        # See if there is a part after this
        for part in disk.partitions:
            geom = part.geometry
            if self.part_offset < geom.start:
                length = geom.end - self.part_offset
                length -= parted.sizeToSectors(1, 'MB', device.sectorSize)
                return parted.Geometry(
                    device=device, start=start, length=length)

        length = device.getLength() - start
        length -= parted.sizeToSectors(1, 'MB', device.sectorSize)
        return parted.Geometry(device=device, start=start, length=length)

    def describe(self):
        return "I should be described by my children. ._."

    def apply(self, disk, simulate):
        """ Create a partition with the given type... """
        try:
            if not disk:
                raise RuntimeError("Cannot create partition on empty disk!")
            length = parted.sizeToSectors(
                self.size, 'B', disk.device.sectorSize)
            geom = parted.Geometry(
                device=self.device, start=self.part_offset, length=length)

            # Don't run off the end of the disk ...
            geom_cmp = self.get_all_remaining_geom(
                disk, disk.device, self.part_offset)

            if geom_cmp.length < geom.length or geom.length < 0:
                geom = geom_cmp

            fs = parted.FileSystem(type=self.fstype, geometry=geom)
            p = parted.Partition(
                disk=disk, type=self.ptype, fs=fs, geometry=geom)

            disk.addPartition(
                p,  parted.Constraint(device=self.device))
            self.part = p
            self.part_end = self.part_offset + length
        except Exception as e:
            self.set_errors(e)
            return False
        return True

    def apply_format(self, disk):
        """ Post-creation all disks must be formatted """
        return False


class DiskOpCreateSwap(DiskOpCreatePartition):
    """ Create a new swap partition """

    def __init__(self, device, ptype, size):
        DiskOpCreatePartition.__init__(
            self,
            device,
            ptype,
            "linux-swap(v1)",
            size)

    def describe(self):
        return "Create {} swap partition on {}".format(
            format_size_local(self.size, True), self.device.path)

    def apply_format(self, disk):
        cmd = "mkswap {}".format(self.part.path)
        try:
            subprocess.check_call(cmd, shell=True)
        except Exception as e:
            self.set_errors("{}: {}".format(self.part.path, e))
            return False
        return True


class DiskOpCreateESP(DiskOpCreatePartition):
    """ Create a new ESP """

    def __init__(self, device, ptype, size):
        DiskOpCreatePartition.__init__(
            self,
            device,
            ptype,
            "fat32",
            size)

    def describe(self):
        return "Create {} EFI System Partition on {}".format(
            format_size_local(self.size, True), self.device.path)

    def apply(self, disk, simulate):
        """ Create the fat partition first """
        b = DiskOpCreatePartition.apply(self, disk, simulate)
        if not b:
            return b
        try:
            self.part.setFlag(parted.PARTITION_BOOT)
        except Exception as e:
            self.set_errors("Cannot set ESP type: {}".format(e))
            return False
        return True

    def apply_format(self, disk):
        cmd = "mkdosfs -F 32 {}".format(self.part.path)
        try:
            subprocess.check_call(cmd, shell=True)
        except Exception as e:
            self.set_errors("{}: {}".format(self.part.path, e))
            return False
        return True


class DiskOpCreateRoot(DiskOpCreatePartition):
    """ Create a new root partition """

    def __init__(self, device, ptype, size):
        DiskOpCreatePartition.__init__(
            self,
            device,
            ptype,
            "ext4",
            size)

    def describe(self):
        return "Create {} root partition on {}".format(
            format_size_local(self.size, True), self.device.path)

    def apply_format(self, disk):
        cmd = "mkfs.ext4 -F {}".format(self.part.path)
        try:
            subprocess.check_call(cmd, shell=True)
        except Exception as e:
            self.set_errors("{}: {}".format(self.part.path, e))
            return False
        return True

    def apply(self, disk, simulate):
        """ Create root partition  """
        b = DiskOpCreatePartition.apply(self, disk, simulate)
        if not b:
            return b
        if disk.type != "msdos":
            return True
        try:
            self.part.setFlag(parted.PARTITION_BOOT)
        except Exception as e:
            self.set_errors("Cannot set root as bootable: {}".format(e))
            return False
        return True


class DiskOpUseSwap(BaseDiskOp):
    """ Use an existing swap paritition """

    swap_part = None
    path = None

    def __init__(self, device, swap_part):
        BaseDiskOp.__init__(self, device)
        self.swap_part = swap_part
        self.path = self.swap_part.path

    def describe(self):
        return "Use {} as swap partition".format(self.swap_part.path)

    def apply(self, disk, simulate):
        """ Can't actually fail here. """
        return True


class DiskOpResizeOS(BaseDiskOp):
    """ Resize an operating system """

    their_size = None
    our_size = None
    desc = None
    part = None
    new_part_off = None

    def __init__(self, device, part, os, their_size, our_size):
        BaseDiskOp.__init__(self, device)

        self.their_size = their_size
        self.our_size = our_size
        self.part = part.partition

        their_new_sz = format_size_local(their_size, True)
        their_old_sz = format_size_local(part.size, True)

        self.desc = "Resize {} ({}) from {} to {}".format(
            os, part.path, their_old_sz, their_new_sz)

    def describe(self):
        return self.desc

    def get_size_constraint(self, disk, new_len):
        """ Gratefully borrowed from blivet, Copyright (C) 2009 Red Hat
            https://github.com/rhinstaller/blivet/
        """
        current_geom = self.part.geometry
        current_dev = current_geom.device
        new_geometry = parted.Geometry(device=current_dev,
                                       start=current_geom.start,
                                       length=new_len)

        # and align the end sector
        alignment = disk.partitionAlignment
        if new_geometry.length < current_geom.length:
            align = alignment.alignUp
            align_geom = current_geom  # we can align up into the old geometry
        else:
            align = alignment.alignDown
            align_geom = new_geometry

        new_geometry.end = align(align_geom, new_geometry.end)
        constraint = parted.Constraint(exactGeom=new_geometry)
        return (constraint, new_geometry)

    def apply(self, disk, simulate):
        try:
            nlen = parted.sizeToSectors(self.their_size,
                                        'B', disk.device.sectorSize)
            cmd = None

            if self.part.fileSystem.type == "ntfs":
                newSz = str(int(self.their_size) / 1000)

                prefix = "/usr/sbin"
                check_cmd = "{}/ntfsresize -i -f --force -v {} {}".format(
                    prefix,
                    "--no-action" if simulate else "", self.part.path)

                resize_cmd = "{}/ntfsresize {} -f -f -b --size {}k {}".format(
                    prefix,
                    "--no-action" if simulate else "", newSz, self.part.path)

                # Check first
                try:
                    subprocess.check_call(check_cmd, shell=True)
                except Exception as e:
                    self.set_errors(e)
                    return False

                # Now resize it
                try:
                    subprocess.check_call(resize_cmd, shell=True)
                except Exception as e:
                    self.set_errors(e)
                    return False

                (c, geom) = self.get_size_constraint(disk, nlen)
                self.part.disk.setPartitionGeometry(partition=self.part,
                                                    constraint=c,
                                                    start=geom.start,
                                                    end=geom.end)
                self.new_part_off = geom.end
                # All done
                return True
            elif self.part.fileSystem.type.startswith("ext"):
                if simulate:
                    (c, geom) = self.get_size_constraint(disk, nlen)
                    self.part.disk.setPartitionGeometry(partition=self.part,
                                                        constraint=c,
                                                        start=geom.start,
                                                        end=geom.end)
                    self.new_part_off = geom.end
                    return True
                # check it first
                cmd1 = "/sbin/e2fsck -f -p {}".format(self.part.path)
                try:
                    subprocess.check_call(cmd1, shell=True)
                except Exception as ex:
                    print(ex)
                    self.set_errors(ex)
                    return False

                new_size = str(int(self.their_size / 1024))
                cmd = "/sbin/resize2fs {} {}K".format(
                    self.part.path, new_size)
                try:
                    subprocess.check_call(cmd, shell=True)
                except Exception as ex:
                    print(ex)
                    self.set_errors(ex)
                    return False

                (c, geom) = self.get_size_constraint(disk, nlen)
                self.part.disk.setPartitionGeometry(partition=self.part,
                                                    constraint=c,
                                                    start=geom.start,
                                                    end=geom.end)
                self.new_part_off = geom.end
            else:
                return False
        except Exception as e:
            self.set_errors(e)
            return False
        return True


class DiskOpFormatPartition(BaseDiskOp):
    """ Format one thing as another """

    format_type = None
    part = None

    def __init__(self, device, part, format_type):
        BaseDiskOp.__init__(self, device)
        self.part = part
        self.format_type = format_type

    def describe(self):
        return "Format {} as {}".format(self.part.path, self.format_type)


class DiskOpFormatRoot(DiskOpFormatPartition):
    """ Format the root partition """

    def __init__(self, device, part):
        DiskOpFormatPartition.__init__(self, device, part, "ext4")

    def describe(self):
        return "Format {} as {} root partition".format(
            self.part.path, self.format_type)

    def apply(self, disk, simulate):
        if simulate:
            return True

        cmd = "mkfs.ext4 -F {}".format(self.part.path)
        try:
            subprocess.check_call(cmd, shell=True)
        except Exception as e:
            self.set_errors("{}: {}".format(self.part.path, e))
            return False
        return True


class DiskOpFormatSwap(DiskOpFormatPartition):
    """ Format the swap partition """

    def __init__(self, device, part):
        DiskOpFormatPartition.__init__(self, device, part, "swap")

    def describe(self):
        return "Use {} as {} swap partition".format(
            self.part.path, self.format_type)

    def apply(self, disk, simulate):
        if simulate:
            return True

        cmd = "mkswap {}".format(self.part.path)
        try:
            subprocess.check_call(cmd, shell=True)
        except Exception as e:
            self.set_errors("{}: {}".format(self.part.path, e))
            return False
        return True


class DiskOpFormatHome(DiskOpFormatPartition):
    """ Format the home partition """

    def __init__(self, device, part):
        DiskOpFormatPartition.__init__(self, device, part, "ext4")

    def describe(self):
        return "Format {} as {} home partition".format(
            self.part.path, self.format_type)

    def apply(self, disk, simulate):
        if simulate:
            return True

        cmd = "mkfs.ext4 -F {}".format(self.part.path)
        try:
            subprocess.check_call(cmd, shell=True)
        except Exception as e:
            self.set_errors("{}: {}".format(self.part.path, e))
            return False
        return True


class DiskOpUseHome(BaseDiskOp):
    """ Use an existing home paritition """

    home_part = None
    home_part_fs = None
    path = None

    def __init__(self, device, home_part, home_part_fs):
        BaseDiskOp.__init__(self, device)
        self.home_part = home_part
        self.path = self.home_part.path
        self.home_part_fs = home_part_fs

    def describe(self):
        return "Use {} ({}) as home partition".format(self.home_part.path,
                                                      self.home_part_fs)

    def apply(self, disk, simulate):
        """ Can't actually fail here. """
        return True
