"use client";

// Primitivo shadcn/ui (Radix Slider), amarrado aos tokens --primary/--secondary.
// Ver docs/planejamento/design-system-projmap-ui.md (mapeamento de tokens).

import * as SliderPrimitive from "@radix-ui/react-slider";
import * as React from "react";
import { cn } from "../../lib/utils";

type SliderProps = React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> & {
  "aria-label"?: string;
};

const Slider = React.forwardRef<React.ElementRef<typeof SliderPrimitive.Root>, SliderProps>(
  ({ className, "aria-label": ariaLabel, ...props }, ref) => (
    <SliderPrimitive.Root
      ref={ref}
      className={cn("relative flex w-full touch-none select-none items-center", className)}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-secondary">
        <SliderPrimitive.Range className="absolute h-full bg-primary" />
      </SliderPrimitive.Track>
      {(props.value ?? props.defaultValue ?? [0]).map((_, i) => (
        <SliderPrimitive.Thumb
          key={i}
          aria-label={ariaLabel}
          className="block h-3.5 w-3.5 rounded-full border-2 border-primary bg-primary-foreground shadow transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
        />
      ))}
    </SliderPrimitive.Root>
  ),
);
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };
