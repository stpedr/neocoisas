"use client";

// Primitivo shadcn/ui Dialog (Radix @radix-ui/react-dialog) + Framer Motion
// no backdrop e no painel modal (substitui .gallery-backdrop + .gallery/.dialog).

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import * as React from "react";
import { cn } from "../../lib/utils";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => {
  const reduce = useReducedMotion();
  return (
    <DialogPrimitive.Overlay ref={ref} asChild {...props}>
      <motion.div
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className={cn(
          "fixed inset-0 z-50 bg-black/60",
          className,
        )}
      />
    </DialogPrimitive.Overlay>
  );
});
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => {
  const reduce = useReducedMotion();
  return (
    <AnimatePresence>
      <DialogPortal key="dialog-portal">
        <DialogOverlay />
        <DialogPrimitive.Content
          ref={ref}
          aria-describedby={undefined}
          asChild
          {...props}
        >
          <motion.div
            initial={reduce ? false : { opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className={cn(
              "fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-24px)] w-[min(980px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 flex-col gap-2.5 overflow-y-auto rounded-radius border border-border bg-card p-3.5 text-card-foreground shadow-lg focus:outline-none",
              className,
            )}
          >
            {children}
          </motion.div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </AnimatePresence>
  );
});
DialogContent.displayName = DialogPrimitive.Content.displayName;

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div
    className={cn(
      "sticky -top-3.5 z-10 flex items-center justify-between gap-2 bg-card py-1",
      className,
    )}
    {...props}
  />
);
DialogHeader.displayName = "DialogHeader";

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("m-0 text-[13px] font-semibold tracking-wide text-foreground", className)}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
};
