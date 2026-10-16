"use client";

// Primitivo shadcn/ui — equivalente ao `input, select { ... }` genérico do
// CSS legado, pra inputs de texto/número.

import * as React from "react";
import { cn } from "../../lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "h-9 min-w-0 rounded-md border border-border bg-secondary px-2 text-sm text-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
