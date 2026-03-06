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
