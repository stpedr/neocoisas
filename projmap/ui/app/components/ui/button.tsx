"use client";

// Primitivo shadcn/ui. Variantes espelham o que .btn/.btn-accent/.btn-danger
// já faziam — ver docs/planejamento/design-system-projmap-ui.md.

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-radius-sm text-sm font-semibold transition-colors disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
  {
    variants: {
      variant: {
        default: "bg-secondary text-secondary-foreground border border-border hover:border-primary",
        primary: "bg-primary text-primary-foreground hover:opacity-90",
        destructive: "bg-destructive/15 text-destructive border border-destructive hover:bg-destructive/25",
        outline: "border border-border bg-transparent text-foreground hover:border-primary",
        ghost: "bg-transparent text-foreground hover:bg-secondary",
      },
      size: {
        default: "h-9 px-3 py-1.5",
        sm: "h-[30px] px-2.5 text-xs",
        block: "h-9 w-full px-3 py-1.5",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
