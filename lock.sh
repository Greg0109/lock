#!/bin/bash

# Wayland lock screen with custom effects
# For Ubuntu 24.04 GNOME:
# sudo apt install i3lock-color imagemagick grim

icon="$HOME/Documentos/lock/lock.png"
img=$(mktemp /tmp/XXXXXXXXXX.png)

# Take a screenshot of current desktop (Wayland)
if ! grim $img 2>/dev/null; then
    # Fallback to gnome-screenshot if grim fails
    gnome-screenshot -f $img 2>/dev/null
fi

# Check if screenshot was captured successfully
if [ ! -s "$img" ]; then
    echo "Error: Failed to capture screenshot"
    rm $img
    exit 1
fi

# Pixelate the screenshot
convert $img -scale 10% -scale 1000% $img

# Blur the screenshot
convert $img -blur 2,5 $img

# Add the lock image (if it exists)
if [ -f "$icon" ]; then
    convert $img $icon -gravity center -composite $img
fi

# Use i3lock-color (enhanced version with better features)
if command -v i3lock-color &> /dev/null; then
    i3lock-color -n -i $img
# Fallback to i3lock
elif command -v i3lock &> /dev/null; then
    i3lock -n -i $img
else
    echo "Error: No screen lock utility found. Install i3lock-color:"
    echo "  sudo apt install i3lock-color"
    rm $img
    exit 1
fi

# Remove the tmp file
rm $img
