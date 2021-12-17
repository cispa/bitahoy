# Raspberry Pi image specs

This repository contains the files with which the images referenced at
https://wiki.debian.org/RaspberryPiImages have been built.

## Building your own image

If you prefer, you can build a Debian buster Raspberry Pi image
yourself. If you are reading this document online, you should first
clone this repository:

```shell
git clone --recursive https://salsa.debian.org/raspi-team/image-specs.git
cd image-specs
```

For this you will first need to install the following packages on a
Debian Buster (10) or higher system:

* vmdb2 (>= 0.17)
* dosfstools
* binfmt-support
* qemu-utils
* qemu-user-static
* debootstrap
* time
* kpartx
* fakemachine (optional, only available on amd64)

To install these (as root):
```shell
   apt install -y vmdb2 dosfstools qemu-utils qemu-user-static debootstrap binfmt-support time kpartx
   apt install -y fakemachine
```

Do note that –at least currently– vmdb2 uses some syntax that is available
only in the version in testing (Bullseye).

If debootstrap still fails with exec format error, try
running `dpkg-reconfigure qemu-user-static`. This calls
`/var/lib/dpkg/info/qemu-user-static.postinst` which uses binfmt-support
to register the executable format with /usr/bin/qemu-$fmt-static

This repository includes a master YAML recipe (which is basically a
configuration file) for all of the generated images, diverting as
little as possible in a parametrized way. The master recipe is
[raspi_master.yaml](raspi_master.yaml).

A Makefile is supplied to drive the build of the recipes into images.
If `fakemachine` is installed, it can be run as an unprivileged user.
Otherwise, because some steps of building the image require root privileges,
you'll need to execute `make` as root.


So if you want to build the default image for a Raspberry Pi 4, you can just issue:

```shell
   make watchdog.img
```

This will first create a `watchdog.yaml` file and then use that
*yaml* recipe to build the image with `vmdb2`.

You can also edit the `yaml` file to customize the built image. If you
want to start from the platform-specific recipe, you can issue:

```shell 
make watchdog.yaml 
``` 
The recipe drives [vmdb2](https://vmdb2.liw.fi/), the successor to
`vmdebootstrap`. Please refer to [its
documentation](https://vmdb2.liw.fi/documentation/) for further details;
it is quite an easy format to understand.

Copy the generated file to a name descriptive enough for you (say,
`my_raspi_bullseye.yaml`). Once you have edited the recipe for your
specific needs, you can generate the image by issuing the following (as
root):

```shell
vmdb2 --rootfs-tarball=my_raspi_bullseye.tar.gz --output \
my_raspi_bullseye.img my_raspi_bullseye.yaml --log my_raspi_bullseye.log
```

This is, just follow what is done by the `_build_img` target of the
Makefile.

## Installing the image onto the Raspberry Pi

Plug an SD card which you would like to entirely overwrite into your SD card reader.

Assuming your SD card reader provides the device `/dev/mmcblk0`
(**Beware** If you choose the wrong device, you might overwrite
important parts of your system.  Double check it's the correct
device!), copy the image onto the SD card:

```shell
sudo dd if=watchdog.img of=/dev/mmcblk0 bs=64k oflag=dsync status=progress
```

Then, plug the SD card into the Raspberry Pi, and power it up.

The image uses the hostname `rpi0w`, `rpi2`, `rpi3`, or `rpi4` depending on the
target build. The provided image will allow you to log in with the
`root` account with no password set, but only logging in at the
physical console (be it serial or by USB keyboard and HDMI monitor).


## WSL qemu fix

`sudo service binfmt-support start`