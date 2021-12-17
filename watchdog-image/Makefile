all: shasums


platforms := watchdog

shasums: $(addsuffix .sha256,$(platforms)) $(addsuffix .xz.sha256,$(platforms))
xzimages: $(addsuffix .img.xz,$(platforms))
images: $(addsuffix .img,$(platforms))
yaml: $(addsuffix .yaml,$(platforms))

ifeq ($(shell id -u),0)
as_root =
else ifneq (,$(wildcard /usr/bin/fakemachine))
$(warning "This should normally be run as root, but found 'fakemachine', so using that.")
as_root = fakemachine -v $(CURDIR) -- env --chdir $(CURDIR)
else
$(error "This must be run as root")
endif

target_platforms:
	@echo $(platforms)


watchdog_setup: 
	@. ~/.cargo/env && cd watchdog-setup && cargo build --target=aarch64-unknown-linux-musl && cd .. && cp watchdog-setup/target/aarch64-unknown-linux-musl/debug/watchdog-setup watchdog_setup

deploy_key:
	@. ssh-keygen -t ed25519 -C "watchdog-image-$(date +%Y%m%d)" -f deploy_key -N ""

watchdog.yaml: watchdog_setup deploy_key
	cat yaml/raspi_base_bullseye.yaml | sed "s/__ARCH__/arm64/" | \
	sed "s#cmdline.txt#cmdline.txt\n      sed -i 's/cma=64M //' /boot/firmware/cmdline.txt\n      sed -i 's/cma=\\\$$CMA //' /etc/kernel/postinst.d/z50-raspi-firmware#" | \
	sed "s/__LINUX_IMAGE__/linux-image-arm64/" | \
	sed "s/__EXTRA_PKGS__/- firmware-brcm80211/" | \
	sed "s/__DTB__/\\/usr\\/lib\\/linux-image-*-arm64\\/broadcom\\/bcm*rpi*.dtb/" |\
	sed "s/__SERIAL_CONSOLE__/ttyS1,115200/" |\
	sed "s/__HOST__/bitahoywatchdog/" |\
	grep -v '__EXTRA_SHELL_CMDS__' > $@

%.sha256: %.img
	echo $@
	sha256sum $(@:sha256=img) > $@

%.xz.sha256: %.img.xz
	echo $@
	sha256sum $(@:xz.sha256=img.xz) > $@

%.img.xz: %.img
	xz -f -k -z -9 $(@:.xz=)

%.img: %.yaml
	touch $(@:.img=.log)
	time nice $(as_root) vmdb2 --verbose --rootfs-tarball=$(subst .img,.tar.gz,$@) --output=$@ $(subst .img,.yaml,$@) --log $(subst .img,.log,$@)
	chmod 0644 $@ $(@,.img=.log)


_ck_root:
	[ `whoami` = 'root' ] # Only root can summon vmdb2 ☹

_clean_yaml:
	rm -f $(addsuffix .yaml,$(platforms)) raspi_base_buster.yaml raspi_base_bullseye.yaml
_clean_images:
	rm -f $(addsuffix .img,$(platforms))
_clean_xzimages:
	rm -f $(addsuffix .img.xz,$(platforms))
_clean_shasums:
	rm -f $(addsuffix .sha256,$(platforms)) $(addsuffix .xz.sha256,$(platforms))
_clean_logs:
	rm -f $(addsuffix .log,$(platforms))
_clean_tarballs:
	rm -f $(addsuffix .tar.gz,$(platforms))
clean: _clean_xzimages _clean_images _clean_shasums _clean_yaml _clean_tarballs _clean_logs

.PHONY: _ck_root _build_img clean _clean_images _clean_yaml _clean_tarballs _clean_logs
