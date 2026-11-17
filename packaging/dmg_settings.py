# Layout of the Mac disk image, read by dmgbuild (https://dmgbuild.readthedocs.io), which writes the Finder layout
# directly, with no AppleScript, so it works on a build machine without a logged-in Finder.
#   dmgbuild -s packaging/dmg_settings.py -D app=dist/bracket.app "bracket" out/bracket-macos.dmg
import os.path

app = defines.get("app", "dist/bracket.app")  # noqa: F821  (dmgbuild provides `defines`)
appname = os.path.basename(app)

format = "UDZO"
files = [app]
symlinks = {"Applications": "/Applications"}
icon = "build/icon.icns"                       # the volume's own icon, shown on the desktop while mounted
background = "build/dmg-background.tiff"       # 1x and 2x in one file (made with tiffutil on the Mac)
window_rect = ((200, 140), (640, 400))
default_view = "icon-view"
show_status_bar = show_tab_view = show_toolbar = show_pathbar = show_sidebar = False
icon_size = 112
text_size = 13
icon_locations = {appname: (170, 215), "Applications": (470, 215)}
hide_extensions = [appname]
