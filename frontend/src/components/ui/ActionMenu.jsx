// src/components/ui/ActionMenu.jsx

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MoreVertical } from "lucide-react";
import { cn } from "../../utils/classNames.js";

const MENU_WIDTH = 192; // matches w-48
const ITEM_HEIGHT = 40;
const MENU_PADDING = 8;
const GAP = 4;

/**
 * Three-dot dropdown menu.
 * items: [{ label, icon: LucideIcon, onClick, danger?: boolean }]
 *
 * Renders its dropdown through a portal into document.body (position:
 * fixed, coordinates computed from the button's bounding rect) instead of
 * as a normal absolutely-positioned child. This is deliberate: table
 * wrappers use `overflow-x-auto` for horizontal scrolling, but per the CSS
 * overflow spec, setting overflow-x to a non-visible value forces
 * overflow-y to become 'auto' too — so a plain absolutely-positioned
 * dropdown ends up trapped inside that scroll box (showing a scrollbar or
 * getting clipped) instead of floating freely above the page. Using a
 * portal sidesteps that entirely.
 */
export default function ActionMenu({ items = [], align = "right" }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState(null);
  const buttonRef = useRef(null);
  const menuRef = useRef(null);

  const computePosition = () => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const menuHeight = items.length * ITEM_HEIGHT + MENU_PADDING;
    const openUpward = window.innerHeight - rect.bottom < menuHeight;

    setCoords({
      top: openUpward ? rect.top - menuHeight - GAP : rect.bottom + GAP,
      left: align === "right" ? rect.right - MENU_WIDTH : rect.left,
    });
  };

  const handleToggle = (e) => {
    e.stopPropagation();
    setOpen((v) => {
      const next = !v;
      if (next) computePosition();
      return next;
    });
  };

  useEffect(() => {
    function handleClickOutside(e) {
      const clickedButton = buttonRef.current?.contains(e.target);
      const clickedMenu = menuRef.current?.contains(e.target);
      if (!clickedButton && !clickedMenu) setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!open) return;
    window.addEventListener("scroll", computePosition, true);
    window.addEventListener("resize", computePosition);
    return () => {
      window.removeEventListener("scroll", computePosition, true);
      window.removeEventListener("resize", computePosition);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={handleToggle}
        className="p-1.5 rounded-btn hover:bg-slate-100 transition-colors"
        aria-label="More actions"
      >
        <MoreVertical className="w-4 h-4 text-slate-400" />
      </button>

      {open &&
        coords &&
        createPortal(
          <div
            ref={menuRef}
            style={{ top: coords.top, left: coords.left, width: MENU_WIDTH }}
            className="fixed bg-white border border-slate-100 rounded-card shadow-lg py-1 z-50"
          >
            {items.map((item, i) => (
              <button
                key={i}
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  item.onClick?.();
                  setOpen(false);
                }}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3.5 py-2 text-sm text-left transition-colors",
                  item.danger
                    ? "text-red-600 hover:bg-red-50"
                    : "text-slate-600 hover:bg-slate-50",
                )}
              >
                {item.icon && <item.icon className="w-4 h-4" />}
                {item.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}
