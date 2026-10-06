# Supply x86-64 musl-linked VBoxService/VBoxControl built from Oracle sources.
# Do not copy the glibc binaries from a Guest Additions ISO into this directory.
include $(TOPDIR)/rules.mk
PKG_NAME:=serviceready-vbox-tools
PKG_VERSION:=7.2.18
PKG_RELEASE:=1
PKG_LICENSE:=GPL-3.0-only
include $(INCLUDE_DIR)/package.mk

define Package/serviceready-vbox-tools
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=INSAP VirtualBox guest userspace tools
  DEPENDS:=@TARGET_x86_64 +kmod-serviceready-vboxguest +libstdcpp +zlib
endef

define Build/Prepare
	$(call Build/Prepare/Default)
	test -f ./files/VBoxService -a -f ./files/VBoxControl -a -f ./files/COPYING
	! $(TARGET_CROSS)readelf -l ./files/VBoxService ./files/VBoxControl | grep -q ld-linux
endef

define Build/Compile
endef

define Package/serviceready-vbox-tools/install
	$(INSTALL_DIR) $(1)/usr/sbin $(1)/usr/bin $(1)/etc/init.d $(1)/usr/share/licenses/serviceready-vbox-tools
	$(INSTALL_BIN) ./files/VBoxService $(1)/usr/sbin/VBoxService
	$(INSTALL_BIN) ./files/VBoxControl $(1)/usr/bin/VBoxControl
	$(INSTALL_BIN) ./files/serviceready-vbox $(1)/etc/init.d/serviceready-vbox
	$(INSTALL_DATA) ./files/COPYING $(1)/usr/share/licenses/serviceready-vbox-tools/COPYING
endef

$(eval $(call BuildPackage,serviceready-vbox-tools))
