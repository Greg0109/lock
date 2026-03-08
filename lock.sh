#!/bin/bash

# Wayland lock screen with custom effects
#
# For Ubuntu 24.04 GNOME:
#   sudo apt install i3lock-color imagemagick grim
#
# For Pop!_OS 24.04 COSMIC:
#   sudo apt install swaylock imagemagick grim
#   (grim works with COSMIC via wlr-screencopy protocol)
#   If grim fails, the script falls back to XDG Desktop Portal,
#   which requires: sudo apt install python3-dbus python3-gi

icon="$HOME/Documents/lock/lock.png"
img=$(mktemp /tmp/XXXXXXXXXX.png)

# Take a screenshot of current desktop (Wayland/X11)
screenshot_taken=false

# Method 1: grim (wlroots-compatible: sway, COSMIC, etc.)
if ! $screenshot_taken && command -v grim &> /dev/null; then
    if grim "$img" 2>/dev/null; then
        screenshot_taken=true
    fi
fi

# Method 2: gnome-screenshot (GNOME Wayland/X11)
if ! $screenshot_taken && command -v gnome-screenshot &> /dev/null; then
    if gnome-screenshot -f "$img" 2>/dev/null; then
        screenshot_taken=true
    fi
fi

# Method 3: spectacle (KDE Plasma)
if ! $screenshot_taken && command -v spectacle &> /dev/null; then
    if spectacle -b -n -f -o "$img" 2>/dev/null; then
        screenshot_taken=true
    fi
fi

# Method 4: XDG Desktop Portal (universal Wayland fallback - COSMIC, GNOME, KDE)
if ! $screenshot_taken && command -v python3 &> /dev/null; then
    SCREENSHOT_OUTPUT="$img" python3 << 'PYEOF'
import os, sys, shutil
from urllib.parse import urlparse, unquote
try:
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    loop = GLib.MainLoop()
    result_uri = [None]
    def on_response(response, results):
        if response == 0 and 'uri' in results:
            result_uri[0] = str(results['uri'])
        loop.quit()
    portal = bus.get_object('org.freedesktop.portal.Desktop',
                            '/org/freedesktop/portal/desktop')
    iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')
    request_path = iface.Screenshot('', {'interactive': dbus.Boolean(False)})
    bus.add_signal_receiver(on_response,
        signal_name='Response',
        dbus_interface='org.freedesktop.portal.Request',
        path=request_path)
    GLib.timeout_add_seconds(5, loop.quit)
    loop.run()
    if result_uri[0]:
        src = unquote(urlparse(result_uri[0]).path)
        shutil.copy2(src, os.environ['SCREENSHOT_OUTPUT'])
        sys.exit(0)
except Exception:
    pass
sys.exit(1)
PYEOF
    if [ $? -eq 0 ] && [ -s "$img" ]; then
        screenshot_taken=true
    fi
fi

# Method 5: scrot (X11 fallback)
if ! $screenshot_taken && command -v scrot &> /dev/null; then
    if scrot "$img" 2>/dev/null; then
        screenshot_taken=true
    fi
fi

# Method 6: import from ImageMagick (X11 fallback)
if ! $screenshot_taken && command -v import &> /dev/null; then
    if import -window root "$img" 2>/dev/null; then
        screenshot_taken=true
    fi
fi

# Check if screenshot was captured successfully
if ! $screenshot_taken || [ ! -s "$img" ]; then
    echo "Error: Failed to capture screenshot. Install one of:"
    echo "  COSMIC/wlroots: sudo apt install grim"
    echo "  GNOME:          sudo apt install gnome-screenshot"
    echo "  KDE:            sudo apt install spectacle"
    echo "  X11:            sudo apt install scrot"
    rm -f "$img"
    exit 1
fi

# Pixelate the screenshot
convert $img -scale 10% -scale 1000% $img

# Blur the screenshot
convert $img -blur 2,5 $img

# Add the lock image (if it exists) - centered on each display
if [ -f "$icon" ]; then
    # Try to get display information for multi-monitor setup
    displays=""
    
    # Try wlr-randr first (works with wlroots compositors)
    if command -v wlr-randr &> /dev/null; then
        displays=$(wlr-randr | grep -E "^[A-Z].*enabled" | awk '{print $1}')
    fi
    
    # Try xrandr as fallback (works with XWayland)
    if [ -z "$displays" ] && command -v xrandr &> /dev/null; then
        displays=$(xrandr --query | grep " connected" | awk '{print $1}')
    fi
    
    if [ -n "$displays" ]; then
        # Get icon dimensions
        icon_width=$(identify -format "%w" "$icon")
        icon_height=$(identify -format "%h" "$icon")
        
        # Get dimensions and positions of each display
        readarray -t display_array <<< "$displays"
        
        for display in "${display_array[@]}"; do
            # Get display geometry (try wlr-randr first)
            if command -v wlr-randr &> /dev/null; then
                geometry=$(wlr-randr | grep -A20 "^$display" | grep "current" | sed 's/.*current //' | awk '{print $1}')
                position=$(wlr-randr | grep -A20 "^$display" | grep "Position" | awk '{print $2}')
            elif command -v xrandr &> /dev/null; then
                info=$(xrandr --query | grep "^$display connected")
                geometry=$(echo "$info" | grep -oP '\d+x\d+\+\d+\+\d+' | head -1)
                if [ -n "$geometry" ]; then
                    position=$(echo "$geometry" | grep -oP '\+\d+\+\d+' | sed 's/+/ /g')
                    geometry=$(echo "$geometry" | grep -oP '^\d+x\d+')
                fi
            fi
            
            if [ -n "$geometry" ]; then
                # Parse geometry (WIDTHxHEIGHT) and position (+X+Y)
                width=$(echo "$geometry" | cut -d'x' -f1)
                height=$(echo "$geometry" | cut -d'x' -f2 | cut -d'+' -f1)
                
                if [ -n "$position" ]; then
                    x_offset=$(echo "$position" | awk '{print $1}')
                    y_offset=$(echo "$position" | awk '{print $2}')
                else
                    x_offset=0
                    y_offset=0
                fi
                
                # Calculate center of this display (accounting for icon size)
                center_x=$((x_offset + (width - icon_width) / 2))
                center_y=$((y_offset + (height - icon_height) / 2))
                
                # Composite the icon at this position (using NorthWest gravity for absolute positioning)
                convert $img $icon -geometry +${center_x}+${center_y} -gravity NorthWest -composite $img
            fi
        done
    else
        # Fallback: single display or detection failed
        convert $img $icon -gravity center -composite $img
    fi
fi

# Lock the screen with the processed image
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    # Wayland: use swaylock (works with COSMIC, sway, etc.)
    if command -v swaylock &> /dev/null; then
        swaylock -f -i "$img"
    else
        echo "Error: No Wayland-compatible lock utility found."
        echo "  sudo apt install swaylock"
        rm -f "$img"
        exit 1
    fi
else
    # X11: use i3lock-color or i3lock
    if command -v i3lock-color &> /dev/null; then
        i3lock-color -n -i "$img"
    elif command -v i3lock &> /dev/null; then
        i3lock -n -i "$img"
    else
        echo "Error: No screen lock utility found."
        echo "  sudo apt install i3lock-color"
        rm -f "$img"
        exit 1
    fi
fi

# Remove the tmp file
rm $img
