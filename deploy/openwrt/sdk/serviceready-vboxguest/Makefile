# Build inside the matching OpenWrt kernel build tree (not a target VM).
include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk
PKG_NAME:=serviceready-vboxguest
PKG_RELEASE:=1
include $(INCLUDE_DIR)/package.mk

define KernelPackage/serviceready-vboxguest
  SUBMENU:=Virtualization support
  TITLE:=INSAP VirtualBox guest kernel support
  DEPENDS:=@TARGET_x86 +kmod-nls-utf8
  KCONFIG:=CONFIG_VBOXGUEST=m CONFIG_VBOXSF_FS=m
  FILES:=$(LINUX_DIR)/drivers/virt/vboxguest/vboxguest.ko $(LINUX_DIR)/fs/vboxsf/vboxsf.ko
  AUTOLOAD:=$(call AutoLoad,90,vboxguest vboxsf)
endef

define Build/Compile
endef

$(eval $(call KernelPackage,serviceready-vboxguest))
